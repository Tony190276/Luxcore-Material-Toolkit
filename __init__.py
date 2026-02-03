bl_info = {
    "name": "LuxCore Material Toolkit",
    "author": "Tony Renzulli",
    "version": (2, 8, 2),
    "blender": (4, 2, 0),
    "location": "Node Editor > Right Click Menu / Sidebar > LuxCore Tools / View3D > Object Context Menu",
    "description": """Tools to speed up setup, conversion and management of materials for LuxCore:
• Automatic PBR Disney setup with PBR textures
• Texture extraction from Cycles/Eevee materials
• Transfer Principled BSDF values to Disney node
• Separate handling for Normal maps and Bump maps
• Reset Emission Strength and connect existing textures""",
    "category": "Material",
    "support": "COMMUNITY",
}

def register():
    # Import and register submodules here, to avoid circular import
    from . import luxcore_disney_setup
    luxcore_disney_setup.register()

    from . import luxcore_texture_extractor
    luxcore_texture_extractor.register()

    from . import luxcore_texture_connect
    luxcore_texture_connect.register()

    from . import luxcore_connect_selected
    luxcore_connect_selected.register()

def unregister():
    # Import and unregister in reverse order
    from . import luxcore_connect_selected
    luxcore_connect_selected.unregister()

    from . import luxcore_texture_connect
    luxcore_texture_connect.unregister()

    from . import luxcore_texture_extractor
    luxcore_texture_extractor.unregister()

    from . import luxcore_disney_setup
    luxcore_disney_setup.unregister()
