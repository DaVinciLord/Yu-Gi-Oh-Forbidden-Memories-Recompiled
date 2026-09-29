"""Make a big model small enough for the PS1 model format (notes/model-replacement.md).

Blender runs it, as Blender reads FBX and glTF and knows how to decimate:

    blender -b --python tools/pc/model_prepare.py -- MODEL.fbx OUT.obj [TRIANGLES] [MESH,MESH...]

It keeps the named meshes (all of them when none are named) in their rest
pose -- no armature, shape keys at their basis -- decimates them together to
about TRIANGLES triangles (1500 by default, as many as tools/pc/model_import.py
takes), and writes a triangulated OBJ with UVs and normals, +Z its front and
+Y up. model_import.py turns the OBJ into a model record.
"""
import sys

import bpy


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(arguments) < 2:
        print(__doc__)
        sys.exit(2)
    source, out = arguments[0], arguments[1]
    target = int(arguments[2]) if len(arguments) > 2 else 1500
    keep = arguments[3].split(",") if len(arguments) > 3 else None

    bpy.ops.wm.read_factory_settings(use_empty=True)
    if source.lower().endswith(".fbx"):
        bpy.ops.import_scene.fbx(filepath=source)
    elif source.lower().endswith((".glb", ".gltf")):
        bpy.ops.import_scene.gltf(filepath=source)
    elif source.lower().endswith(".obj"):
        bpy.ops.wm.obj_import(filepath=source)
    else:
        sys.exit(f"{source}: FBX, glTF or OBJ")
    for thing in list(bpy.context.scene.objects):
        if thing.type != "MESH" or (keep and thing.name not in keep):
            bpy.data.objects.remove(thing)
    meshes = list(bpy.context.scene.objects)
    if not meshes:
        sys.exit(f"{source}: no mesh" + (f" named {', '.join(keep)}" if keep else ""))
    for mesh in meshes:
        bpy.context.view_layer.objects.active = mesh
        if mesh.data.shape_keys:
            mesh.shape_key_clear()
        for modifier in list(mesh.modifiers):
            mesh.modifiers.remove(modifier)
        world = mesh.matrix_world.copy()      # an armature's turn stays with the mesh
        mesh.parent = None
        mesh.matrix_world = world
    triangles = sum(sum(len(p.vertices) - 2 for p in m.data.polygons) for m in meshes)
    for mesh in meshes:
        bpy.context.view_layer.objects.active = mesh
        decimate = mesh.modifiers.new("decimate", "DECIMATE")
        decimate.ratio = min(1.0, target / triangles)
        decimate.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=decimate.name)
        mesh.modifiers.new("triangulate", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier="triangulate")
    print(f"{out}: {sum(len(m.data.polygons) for m in meshes)} triangles from {triangles}")
    bpy.ops.wm.obj_export(filepath=out, export_uv=True, export_normals=True, export_materials=True,
                          apply_modifiers=True, forward_axis="NEGATIVE_Z", up_axis="Y")


main()
