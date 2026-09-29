"""Make a big model small enough for the PS1 model format (notes/model-replacement.md).

Blender runs it, as Blender reads FBX and glTF and knows how to decimate:

    blender -b --python tools/pc/model_prepare.py -- MODEL.fbx OUT.obj [TRIANGLES] [MESH,MESH...] [--symmetric]

It keeps the named meshes (all of them when none are named) in their rest
pose -- no armature, shape keys at their basis -- decimates them together to
about TRIANGLES triangles (1500 by default, as many as tools/pc/model_import.py
takes), and writes a triangulated OBJ with UVs and normals, +Z its front and
+Y up. model_import.py turns the OBJ into a model record.

Before decimating, vertices in the same place are welded: exported models
split a vertex along every UV seam and hard edge, and decimation takes each
split for an opening in the surface, shrinks small parts (an eye, a tooth)
away from it and leaves holes. The UVs are kept per face corner, so the
seams stay. The mesh is then shaded smooth, with edges sharper than 60
degrees kept sharp. --symmetric decimates the two halves of a model that
is symmetric about its X axis alike, so both eyes come out the same.
"""
import math
import sys

import bmesh

import bpy


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    symmetric = "--symmetric" in arguments
    arguments = [a for a in arguments if a != "--symmetric"]
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
    for mesh in meshes:
        size = max(mesh.dimensions) or 1.0
        welded = bmesh.new()
        welded.from_mesh(mesh.data)
        bmesh.ops.remove_doubles(welded, verts=welded.verts, dist=size * 1e-5)
        welded.to_mesh(mesh.data)
        welded.free()
        bpy.ops.object.select_all(action="DESELECT")
        mesh.select_set(True)
        bpy.context.view_layer.objects.active = mesh
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
    triangles = sum(sum(len(p.vertices) - 2 for p in m.data.polygons) for m in meshes)
    for mesh in meshes:
        bpy.context.view_layer.objects.active = mesh
        decimate = mesh.modifiers.new("decimate", "DECIMATE")
        decimate.ratio = min(1.0, target / triangles)
        decimate.use_collapse_triangulate = True
        decimate.use_symmetry = symmetric
        decimate.symmetry_axis = "X"
        bpy.ops.object.modifier_apply(modifier=decimate.name)
        mesh.modifiers.new("triangulate", "TRIANGULATE")
        bpy.ops.object.modifier_apply(modifier="triangulate")
    print(f"{out}: {sum(len(m.data.polygons) for m in meshes)} triangles from {triangles}")
    bpy.ops.wm.obj_export(filepath=out, export_uv=True, export_normals=True, export_materials=True,
                          apply_modifiers=True, forward_axis="NEGATIVE_Z", up_axis="Y")


main()
