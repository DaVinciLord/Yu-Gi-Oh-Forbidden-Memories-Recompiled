// Structured guest-memory compilation using LLVM 21's IR and verifier.
#include "llvm/IR/Constants.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/InlineAsm.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Operator.h"
#include "llvm/IR/Verifier.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Support/JSON.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/raw_ostream.h"
#include <set>
#include <string>

using namespace llvm;

[[noreturn]] static void fail(const Twine &message) {
  errs() << "memories-guest-ir: " << message << '\n';
  exit(1);
}
static json::Object readOptions(StringRef path) {
  auto buffer = MemoryBuffer::getFile(path);
  if (!buffer) fail("cannot read options: " + path);
  auto value = json::parse((*buffer)->getBuffer());
  if (!value) fail(toString(value.takeError()));
  auto *object = value->getAsObject();
  if (!object) fail("options must be an object");
  return std::move(*object);
}
static void writeJSON(StringRef path, json::Object value) {
  std::error_code error;
  raw_fd_ostream output(path, error);
  if (error) fail(error.message());
  output << formatv("{0:2}", json::Value(std::move(value))) << '\n';
}
static std::string typeName(Type *type) {
  if (type->isVoidTy()) return "void";
  if (type->isIntegerTy()) return "i" + std::to_string(type->getIntegerBitWidth());
  if (auto *pointer = dyn_cast<PointerType>(type))
    return pointer->getAddressSpace() == 0 ? "ptr" :
      "ptr addrspace(" + std::to_string(pointer->getAddressSpace()) + ")";
  std::string result; raw_string_ostream stream(result); type->print(stream);
  return result;
}
static void inspect(Module &module, StringRef output) {
  json::Array definitions, globals, declarations;
  json::Object signatures;
  for (auto &global : module.globals())
    if (!global.isDeclaration()) globals.push_back(global.getName().str());
  for (auto &function : module) {
    if (function.hasLocalLinkage()) continue;
    (function.isDeclaration() ? declarations : definitions).push_back(function.getName().str());
    json::Array parameters;
    for (unsigned i = 0; i < function.arg_size(); ++i)
      parameters.push_back(json::Object{{"kind", typeName(function.getFunctionType()->getParamType(i))},
        {"signext", function.hasParamAttribute(i, Attribute::SExt)}});
    signatures[function.getName()] = json::Object{
      {"result", typeName(function.getReturnType())},
      {"result_signext", function.hasRetAttribute(Attribute::SExt)},
      {"parameters", std::move(parameters)}, {"variadic", function.isVarArg()},
      {"definition", !function.isDeclaration()}};
  }
  json::Object result;
  result["definitions"] = std::move(definitions);
  result["globals"] = std::move(globals);
  result["declarations"] = std::move(declarations);
  result["signatures"] = std::move(signatures);
  writeJSON(output, std::move(result));
}
static void renameGlobal(Module &module, GlobalValue *value, StringRef target) {
  if (!value || value->getName() == target) return;
  auto *existing = module.getNamedValue(target);
  if (!existing) { value->setName(target); return; }
  if (value->getValueID() != existing->getValueID() || value->getType() != existing->getType())
    fail("incompatible renamed symbols: " + target);
  if (!value->isDeclaration() && !existing->isDeclaration())
    fail("duplicate renamed definition: " + target);
  // Opaque pointers let differently spelled declarations of one address
  // share its definition; each call retains its own LLVM function type.
  if (!value->isDeclaration()) {
    existing->replaceAllUsesWith(value);
    existing->eraseFromParent();
    value->setName(target);
  } else {
    value->replaceAllUsesWith(existing);
    value->eraseFromParent();
  }
}
static void normalize(Module &module, const json::Object &options) {
  // Gather names before merging, since erasing a declaration invalidates
  // iteration over the module's symbol lists.
  SmallVector<std::pair<std::string, std::string>> assemblerNames;
  for (auto &value : module.global_values()) {
    StringRef name = value.getName();
    if (!name.starts_with("\1")) continue;
    StringRef target = name.drop_front();
    if (target.starts_with("_")) target = target.drop_front();
    assemblerNames.emplace_back(name.str(), target.str());
  }
  for (auto &entry : assemblerNames)
    renameGlobal(module, module.getNamedValue(entry.first), entry.second);
  if (auto *renames = options.getObject("renames"))
    for (auto &entry : *renames) {
      auto target = entry.second.getAsString();
      if (!target) fail("rename target must be a string");
      renameGlobal(module, module.getNamedValue(entry.first), *target);
    }
  if (auto *drop = options.getArray("drop_definitions"))
    for (auto &entry : *drop)
      if (auto name = entry.getAsString())
        if (auto *function = module.getFunction(*name)) {
          function->deleteBody();
          function->setLinkage(GlobalValue::ExternalLinkage);
        }
}

class GuestMemoryPass : public PassInfoMixin<GuestMemoryPass> {
  const json::Object &options;
  Value *encode(IRBuilder<> &builder, Module &module, Value *pointer) {
    auto callee = module.getOrInsertFunction("GuestRuntime_EncodePointer",
      builder.getInt32Ty(), builder.getPtrTy());
    return builder.CreateCall(callee, {pointer});
  }
  Value *guestBits(IRBuilder<> &builder, Value *pointer) {
    auto *type = cast<PointerType>(pointer->getType());
    if (type->getAddressSpace() == 0) return pointer;
    if (type->getAddressSpace() != 271) fail("unsupported pointer address space");
    return builder.CreateIntToPtr(builder.CreatePtrToInt(pointer, builder.getInt32Ty()), builder.getPtrTy());
  }
  Value *resolve(IRBuilder<> &builder, Module &module, Value *pointer, Value *size) {
    auto callee = module.getOrInsertFunction("GuestRuntime_ResolveData",
      builder.getPtrTy(), builder.getPtrTy(), builder.getInt64Ty());
    return builder.CreateCall(callee, {guestBits(builder, pointer), size});
  }
  Value *resolve(IRBuilder<> &builder, Module &module, Value *pointer, Type *type) {
    auto size = module.getDataLayout().getTypeStoreSize(type);
    if (size.isScalable()) fail("scalable memory operation is unsupported");
    return resolve(builder, module, pointer, builder.getInt64(size.getFixedValue()));
  }
  static void materialize(Instruction *instruction) {
    for (unsigned i = 0; i < instruction->getNumOperands(); ++i) {
      if (auto *expression = dyn_cast<ConstantExpr>(instruction->getOperand(i))) {
        auto *expanded = expression->getAsInstruction();
        if (auto *phi = dyn_cast<PHINode>(instruction))
          expanded->insertBefore(phi->getIncomingBlock(i)->getTerminator()->getIterator());
        else expanded->insertBefore(instruction->getIterator());
        instruction->setOperand(i, expanded);
        materialize(expanded);
      }
    }
  }
public:
  explicit GuestMemoryPass(const json::Object &options) : options(options) {}
  PreservedAnalyses run(Module &module, ModuleAnalysisManager &) {
    auto &context = module.getContext();
    if (auto *pins = options.getObject("pins"))
      for (auto &entry : *pins) {
        auto address = entry.second.getAsInteger();
        if (!address || *address < 0 || *address > UINT32_MAX) fail("invalid guest address");
        if (auto *global = module.getNamedGlobal(entry.first)) {
          auto *pointer = ConstantExpr::getIntToPtr(ConstantInt::get(Type::getInt64Ty(context), *address), global->getType());
          global->replaceAllUsesWith(pointer);
          global->eraseFromParent();
        }
      }
    SmallVector<Instruction *> originals;
    for (auto &function : module) for (auto &instruction : instructions(function))
      originals.push_back(&instruction);
    for (auto *instruction : originals) materialize(instruction);
    originals.clear();
    for (auto &function : module) {
      bool twice = function.hasFnAttribute(Attribute::ReturnsTwice);
      function.setAttributes(AttributeList::get(context, AttributeSet(),
        function.getAttributes().getRetAttrs(), [&] {
          SmallVector<AttributeSet> parameters;
          for (unsigned i = 0; i < function.arg_size(); ++i)
            parameters.push_back(function.getAttributes().getParamAttrs(i).removeAttribute(context, Attribute::NoUndef));
          return parameters;
        }()));
      if (twice) function.addFnAttr(Attribute::ReturnsTwice);
      for (auto &instruction : instructions(function)) originals.push_back(&instruction);
    }
    for (auto *instruction : originals) {
      IRBuilder<> builder(instruction);
      SmallVector<std::pair<unsigned, MDNode *>> metadata;
      instruction->getAllMetadata(metadata);
      for (auto &item : metadata) instruction->setMetadata(item.first, nullptr);
      if (auto *gep = dyn_cast<GetElementPtrInst>(instruction)) gep->setNoWrapFlags(GEPNoWrapFlags::none());
      if (auto *binary = dyn_cast<BinaryOperator>(instruction)) {
        if (isa<OverflowingBinaryOperator>(binary)) {
          binary->setHasNoUnsignedWrap(false); binary->setHasNoSignedWrap(false);
        }
      }
      if (auto *castInst = dyn_cast<AddrSpaceCastInst>(instruction)) {
        auto *input = castInst->getOperand(0);
        unsigned from = cast<PointerType>(input->getType())->getAddressSpace();
        unsigned to = cast<PointerType>(castInst->getType())->getAddressSpace();
        Value *value = nullptr;
        if (from == 271 && to == 0) value = guestBits(builder, input);
        else if (from == 0 && to == 271) value = builder.CreateIntToPtr(encode(builder, module, input), castInst->getType());
        else fail("unsupported address-space conversion");
        castInst->replaceAllUsesWith(value); castInst->eraseFromParent(); continue;
      }
      Value *narrow = nullptr;
      if (auto *pointer = dyn_cast<PtrToIntInst>(instruction))
        if (pointer->getType()->isIntegerTy(32) && pointer->getPointerAddressSpace() == 0)
          narrow = pointer->getPointerOperand();
      if (auto *trunc = dyn_cast<TruncInst>(instruction))
        if (trunc->getType()->isIntegerTy(32))
          if (auto *pointer = dyn_cast<PtrToIntInst>(trunc->getOperand(0)))
            if (pointer->getPointerAddressSpace() == 0) narrow = pointer->getPointerOperand();
      if (narrow) {
        instruction->replaceAllUsesWith(encode(builder, module, narrow));
        instruction->eraseFromParent(); continue;
      }
      if (auto *load = dyn_cast<LoadInst>(instruction))
        load->setOperand(0, resolve(builder, module, load->getPointerOperand(), load->getType()));
      else if (auto *store = dyn_cast<StoreInst>(instruction))
        store->setOperand(1, resolve(builder, module, store->getPointerOperand(), store->getValueOperand()->getType()));
      else if (auto *atomic = dyn_cast<AtomicRMWInst>(instruction))
        atomic->setOperand(0, resolve(builder, module, atomic->getPointerOperand(), atomic->getValOperand()->getType()));
      else if (auto *atomic = dyn_cast<AtomicCmpXchgInst>(instruction))
        atomic->setOperand(0, resolve(builder, module, atomic->getPointerOperand(), atomic->getCompareOperand()->getType()));
      else if (auto *call = dyn_cast<CallBase>(instruction)) {
        if (!isa<CallInst>(call)) fail("invoke/callbr are unsupported in guest units");
        if (auto *memory = dyn_cast<MemIntrinsic>(call)) {
          Value *length = builder.CreateZExtOrTrunc(memory->getLength(), builder.getInt64Ty());
          Value *destination = resolve(builder, module, memory->getRawDest(), length);
          CallInst *replacement;
          if (auto *transfer = dyn_cast<MemTransferInst>(memory)) {
            Value *source = resolve(builder, module, transfer->getRawSource(), length);
            replacement = isa<MemMoveInst>(memory) ?
              builder.CreateMemMove(destination, MaybeAlign(), source, MaybeAlign(), length, memory->isVolatile()) :
              builder.CreateMemCpy(destination, MaybeAlign(), source, MaybeAlign(), length, memory->isVolatile());
          } else if (auto *set = dyn_cast<MemSetInst>(memory))
            replacement = builder.CreateMemSet(destination, set->getValue(), length, MaybeAlign(), set->isVolatile());
          else fail("unsupported memory intrinsic");
          (void)replacement; memory->eraseFromParent(); continue;
        }
        if (!call->getCalledFunction() && !call->isInlineAsm()) {
          auto callee = module.getOrInsertFunction("GuestRuntime_ResolveFunction", builder.getPtrTy(), builder.getPtrTy());
          call->setCalledOperand(builder.CreateCall(callee, {guestBits(builder, call->getCalledOperand())}));
        }
        if (call->isInlineAsm()) {
          // Empty compiler barriers do not access guest addresses. Preserve
          // their side effects and memory clobber; reject machine code.
          auto *assembly = cast<InlineAsm>(call->getCalledOperand());
          if (!assembly->getAsmString().empty()) fail("machine assembly is unsupported in translated units");
        }
        auto attrs = call->getAttributes();
        SmallVector<AttributeSet> parameters;
        for (unsigned i = 0; i < call->arg_size(); ++i)
          parameters.push_back(attrs.getParamAttrs(i).removeAttribute(context, Attribute::NoUndef));
        call->setAttributes(AttributeList::get(context, AttributeSet(), attrs.getRetAttrs(), parameters));
        cast<CallInst>(call)->setTailCallKind(CallInst::TCK_None);
      }
    }
    if (auto name = options.getString("registration")) {
      auto *type = FunctionType::get(Type::getVoidTy(context), false);
      auto *function = Function::Create(type, GlobalValue::ExternalLinkage, *name, module);
      IRBuilder<> builder(BasicBlock::Create(context, "entry", function));
      auto callee = module.getOrInsertFunction("GuestRuntime_RegisterGlobal", builder.getVoidTy(), builder.getPtrTy(), builder.getInt64Ty(), builder.getInt64Ty(), builder.getInt32Ty());
      for (auto &global : module.globals()) {
        if (global.isDeclaration() || global.getName().starts_with("llvm.")) continue;
        // Registration gives each global its own guest span. LLVM may
        // otherwise merge unnamed constants and their string suffixes,
        // leaving distinct registered globals overlapping in host memory.
        global.setUnnamedAddr(GlobalValue::UnnamedAddr::None);
        auto size = module.getDataLayout().getTypeAllocSize(global.getValueType());
        if (size.isScalable()) fail("scalable global is unsupported");
        uint64_t identity = 14695981039346656037ull;
        std::string key = module.getSourceFileName() + ":" + global.getName().str();
        for (unsigned char byte : key) { identity ^= byte; identity *= 1099511628211ull; }
        unsigned flags = options.getBoolean("game_unit").value_or(false) ? 2 : 0;
        if (global.isConstant()) flags |= 4;
        if (size.getFixedValue()) builder.CreateCall(callee, {&global, builder.getInt64(size.getFixedValue()),
          builder.getInt64(identity), builder.getInt32(flags)});
      }
      builder.CreateRetVoid();
    }
    return PreservedAnalyses::none();
  }
};

int main(int argc, char **argv) {
  if (argc != 5) fail("usage: memories-guest-ir <inspect|normalize|translate|optimize> input output options.json");
  LLVMContext context; SMDiagnostic error;
  auto module = parseIRFile(argv[2], error, context);
  if (!module) { error.print(argv[0], errs()); return 1; }
  if (module->getSourceFileName() == argv[2]) module->setSourceFileName("memories-input");
  module->setModuleIdentifier(module->getSourceFileName());
  auto options = readOptions(argv[4]);
  StringRef operation(argv[1]);
  if (operation == "inspect") { inspect(*module, argv[3]); return 0; }
  if (operation == "normalize") normalize(*module, options);
  else if (operation == "translate") {
    ModuleAnalysisManager analyses;
    GuestMemoryPass(options).run(*module, analyses);
  } else if (operation != "optimize") fail("unknown operation");
  if (verifyModule(*module, &errs())) fail("invalid transformed module: " + module->getSourceFileName());
  std::error_code outputError; raw_fd_ostream output(argv[3], outputError);
  if (outputError) fail(outputError.message());
  module->print(output, nullptr);
  return 0;
}
