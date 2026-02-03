bl_info = {
    "name": "LuxCore PBR Material Setup",
    "author": "Tony",
    "version": (1, 5, 0),  # Separate bump from normal maps with intermediate Bump node
    "blender": (4, 2, 0),
    "location": "Node Editor > Right Click Menu on a Disney node",
    "description": "Automatic Disney PBR material setup for LuxCoreRender",
    "category": "Material",
    "support": "COMMUNITY",
}

import bpy
import os
import re
from bpy.props import CollectionProperty, StringProperty, BoolProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper
from bpy.types import Operator, Panel, Menu

class LUXCORE_OT_select_pbr_textures(Operator, ImportHelper):
    """Select PBR textures to connect automatically"""
    bl_idname = "luxcore.select_pbr_textures"
    bl_label = "Select PBR Textures"
    bl_options = {'REGISTER', 'UNDO'}
    
    files: CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    )
    
    directory: StringProperty(
        subtype='DIR_PATH',
    )
    
    filter_glob: StringProperty(
        default='*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.tga;*.bmp;*.exr;*.hdr',
        options={'HIDDEN'},
    )
    
    auto_connect: BoolProperty(
        name="Automatic Connection",
        default=True,
    )
    
    force_type: EnumProperty(
        name="Force Texture Type",
        items=[
            ('AUTO', "Auto-recognize", "Automatic recognition"),
            ('COLOR', "Color/Diffuse", "Color texture"),
            ('NORMAL', "Normal Map", "Normal map texture"),
            ('ROUGHNESS', "Roughness", "Roughness texture"),
            ('METALLIC', "Metallic", "Metallic texture"),
            ('SPECULAR', "Specular", "Specular texture"),
            ('DISPLACEMENT', "Displacement", "Displacement/height texture"),
            ('AO', "Ambient Occlusion", "AO texture"),
            ('ORM', "ORM (OcclusionRoughnessMetallic)", "Combined ORM texture"),
            ('ORS', "ORS (OcclusionRoughnessSpecular)", "Combined ORS texture"),
        ],
        default='AUTO'
    )
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        space = context.space_data
        if not space or not space.node_tree:
            self.report({'ERROR'}, "No active node tree!")
            return {'CANCELLED'}
        
        node_tree = space.node_tree
        disney_node = node_tree.nodes.active
        
        # Find LuxCore Material Output node
        material_output = None
        for node in node_tree.nodes:
            if node.bl_idname == 'LuxCoreNodeMatOutput':
                material_output = node
                break
        
        # If not found, also search standard type as fallback
        if not material_output:
            for node in node_tree.nodes:
                if node.type == 'OUTPUT_MATERIAL':
                    material_output = node
                    break
        
        disney_node_types = [
            'LuxCoreNodeMatDisney',
            'LuxCoreNodeMatDisney2',
            'luxcore_material_disney'
        ]
        
        if not disney_node or disney_node.bl_idname not in disney_node_types:
            self.report({'ERROR'}, "Select a LuxCore Disney node!")
            return {'CANCELLED'}
        
        # Fixed values
        normal_strength = 1.0
        displacement_height = 0.01
        
        # **CREATE COMMON 2D MAPPING NODE**
        mapping_node = None
        try:
            # Try different names for 2D Mapping node in LuxCore
            mapping_node_types = [
                'LuxCoreNodeTexMapping2D',
                'LuxCoreNodeMapping2D',
                'luxcore_tex_mapping2d',
                'LuxCoreNodeUV',
            ]
            
            for node_type in mapping_node_types:
                try:
                    mapping_node = node_tree.nodes.new(type=node_type)
                    mapping_node.location = (disney_node.location.x - 900, disney_node.location.y)
                    mapping_node.label = "UV Mapping"
                    break
                except:
                    continue
        except Exception as e:
            self.report({'WARNING'}, f"Cannot create 2D Mapping node: {str(e)}")
        
        # Texture mapping with priority
        texture_mapping = {
            'orm': {
                'keywords': ['orm', 'arm', 'mro',
                           'metallicroughness', 'roughnessmetallic',
                           'occlusionroughnessmetallic', 'ambientroughnessmetallic'],
                'socket': None,
                'color_space': 'Non-Color',
                'is_color': False,
                'is_orm': True,
                'priority': 100
            },
            'ors': {
                'keywords': ['ors', 'occlusionroughnessspecular', 'roughnessspecularocclusion',
                           'specularroughnessocclusion', 'ambientroughnessspecular',
                           'occlusionroughnessgloss', 'roughnessglossocclusion'],
                'socket': None,
                'color_space': 'Non-Color',
                'is_color': False,
                'is_ors': True,
                'priority': 90
            },
            'color': {
                'keywords': ['color', 'diff', 'diffuse', 'albedo', 'basecolor', 'col', 'base', 
                           'basecol', 'diffuse', 'dif', 'dff', 'clr', 'colour'],
                'socket': 'Base Color',
                'color_space': 'sRGB',
                'is_color': True,
                'is_color_map': True,
                'priority': 80
            },
            'emission': {
                'keywords': ['emission', 'emit', 'emissive', 'emiss', 'glow', 'light'],
                'socket': 'Emission',
                'color_space': 'sRGB',
                'is_color': True,
                'is_emission': True,
                'priority': 75
            },
            'normal': {
                'keywords': ['normal', 'norm', 'nrm', 'nor', 'normalmap', 'normal_map', 
                           'normalgl', 'normal_dx', 'normaldx', 'nrml', 'normals',
                           'normal_gl', 'norm_gl'],
                'socket': 'Bump',
                'color_space': 'Non-Color',
                'is_color': False,
                'is_normal': True,
                'priority': 70
            },
            'bump': {
                'keywords': ['bump', 'bmp', 'bump_map', 'bumpmap'],
                'socket': 'Bump',
                'color_space': 'Non-Color',
                'is_color': False,
                'is_bump': True,
                'priority': 65
            },
            'metallic': {
                'keywords': ['metal', 'metallic', 'metallness', 'metalness', 'mtl', 'met', 'metalic'],
                'socket': 'Metallic',
                'color_space': 'Non-Color',
                'is_color': False,
                'priority': 60
            },
            'roughness': {
                'keywords': ['rough', 'roughness', 'rugosità', 'roughness', 'gloss', 'glossiness',
                           'rgh', 'roughness', 'rghns', 'rough', 'rug'],
                'socket': 'Roughness',
                'color_space': 'Non-Color',
                'is_color': False,
                'priority': 50
            },
            'specular': {
                'keywords': ['spec', 'specular', 'specularity', 'spc', 'specular', 'specularlevel'],
                'socket': 'Specular',
                'color_space': 'Non-Color',
                'is_color': False,
                'priority': 40
            },
            'height': {
                'keywords': ['height', 'disp', 'displacement', 'heightmap', 'height_map',
                           'hgt', 'displace', 'depth', 'depthmap'],
                'socket': 'Height',
                'color_space': 'Non-Color',
                'is_color': False,
                'is_height': True,
                'priority': 30
            },
            'opacity': {
                'keywords': ['opacity', 'alpha', 'transparency', 'transparent', 'opac',
                           'alph', 'trans', 'op', 'mask'],
                'socket': 'Opacity',
                'color_space': 'Non-Color',
                'is_color': False,
                'priority': 20
            },
            'ao': {
                'keywords': ['ao', 'ambientocclusion', 'occlusion', 'ambient', 'ambient_occlusion',
                           'occl', 'ambocc', 'ambientoccl', 'occlusion'],
                'socket': None,
                'color_space': 'Non-Color',
                'is_color': False,
                'is_ao': True,
                'priority': 10
            }
        }
        
        # Variables to store special nodes
        color_node = None
        ao_node = None
        normal_nodes = []
        bump_nodes = []
        height_nodes = []
        orm_node = None
        ors_node = None
        orm_ao_channel = None
        ors_ao_channel = None
        
        # Lists to track which texture types are already covered
        covered_types = set()
        
        # List to collect textures to load
        textures_to_load = []
        
        # File handling
        file_list = []
        
        if self.files:
            for file_elem in self.files:
                file_list.append({
                    'path': os.path.join(self.directory, file_elem.name),
                    'name': file_elem.name
                })
        elif self.filepath:
            file_list.append({
                'path': self.filepath,
                'name': os.path.basename(self.filepath)
            })
        else:
            self.report({'ERROR'}, "No file selected!")
            return {'CANCELLED'}
        
        # Identify all textures and their types
        for file_info in file_list:
            filepath = file_info['path']
            filename = file_info['name']
            filename_lower = filename.lower()
            filename_no_ext = os.path.splitext(filename_lower)[0]
            
            # Determine texture type
            tex_type = None
            tex_info = None
            
            for type_key, type_info in texture_mapping.items():
                for keyword in type_info['keywords']:
                    pattern = r'(^|[_-])' + re.escape(keyword) + r'($|[_-])'
                    if re.search(pattern, filename_no_ext):
                        tex_type = type_key
                        tex_info = type_info
                        break
                
                if tex_type:
                    break
            
            # Search for broader patterns
            if not tex_type:
                for type_key, type_info in texture_mapping.items():
                    for keyword in type_info['keywords']:
                        if keyword in filename_no_ext:
                            tex_type = type_key
                            tex_info = type_info
                            break
                    
                    if tex_type:
                        break
            
            # If still not found and user forced a type
            if not tex_type and self.force_type != 'AUTO':
                force_map = {
                    'COLOR': 'color',
                    'NORMAL': 'normal',
                    'ROUGHNESS': 'roughness',
                    'METALLIC': 'metallic',
                    'SPECULAR': 'specular',
                    'DISPLACEMENT': 'height',
                    'AO': 'ao',
                    'ORM': 'orm',
                    'ORS': 'ors'
                }
                if self.force_type in force_map:
                    tex_type = force_map[self.force_type]
                    tex_info = texture_mapping[tex_type]
            
            if not tex_type or not tex_info:
                self.report({'WARNING'}, f"Texture not recognized: {filename}")
                continue
            
            textures_to_load.append({
                'filepath': filepath,
                'filename': filename,
                'type': tex_type,
                'info': tex_info
            })
        
        # Sort textures by priority (descending)
        textures_to_load.sort(key=lambda x: x['info'].get('priority', 0), reverse=True)
        
        loaded_textures = []
        y_offset = 0
        
        # PHASE 1: Loading and connecting textures in priority order
        for tex_data in textures_to_load:
            filepath = tex_data['filepath']
            filename = tex_data['filename']
            tex_type = tex_data['type']
            tex_info = tex_data['info']
            
            print(f"DEBUG: Processing texture: {filename} as {tex_type}")
            
            # Check if this type is already covered by ORM or ORS
            if tex_type in ['metallic', 'roughness', 'ao', 'specular'] and tex_type in covered_types:
                print(f"DEBUG: Texture {tex_type} ({filename}) ignored because already covered by ORM/ORS")
                continue
            
            # If it's ORM, mark that it covers metallic, roughness and ao
            if tex_type == 'orm':
                covered_types.add('metallic')
                covered_types.add('roughness')
                covered_types.add('ao')
                orm_node = tex_data
                print(f"DEBUG: ORM found: {filename}")
            
            # If it's ORS, mark that it covers specular, roughness and ao
            elif tex_type == 'ors':
                covered_types.add('specular')
                covered_types.add('roughness')
                covered_types.add('ao')
                ors_node = tex_data
                print(f"DEBUG: ORS found: {filename}")
            
            # Add current type to covered_types
            covered_types.add(tex_type)
            
            try:
                # Create image node
                tex_node = node_tree.nodes.new(type='LuxCoreNodeTexImagemap')
                tex_node.location = (disney_node.location.x - 600, 
                                    disney_node.location.y + y_offset)
                y_offset -= 280
                
                # Load image
                if filename in bpy.data.images:
                    image = bpy.data.images[filename]
                else:
                    image = bpy.data.images.load(filepath)
                
                tex_node.image = image
                display_name = os.path.splitext(filename)[0]
                tex_node.label = f"{tex_type.upper()}: {display_name[:15]}..."
                
                # Set color space
                if hasattr(tex_node, 'color_space'):
                    tex_node.color_space = tex_info['color_space']
                elif hasattr(tex_node, 'gamma'):
                    tex_node.gamma = 2.2 if tex_info['color_space'] == 'sRGB' else 1.0
                
                # **CONNECT 2D MAPPING NODE TO TEXTURE**
                if mapping_node and self.auto_connect:
                    # Find mapping input in texture
                    mapping_inputs = ['2D Mapping', 'Mapping', 'UV', 'UV Map', 'UVs', 'Vector']
                    
                    mapping_connected = False
                    for input_name in mapping_inputs:
                        if input_name in tex_node.inputs:
                            # Find mapping node output
                            mapping_outputs = ['2D Mapping', 'Mapping', 'UV', 'Vector', 'Output']
                            for output_name in mapping_outputs:
                                if output_name in mapping_node.outputs:
                                    node_tree.links.new(
                                        mapping_node.outputs[output_name],
                                        tex_node.inputs[input_name]
                                    )
                                    mapping_connected = True
                                    tex_node.label += " [UV]"
                                    break
                            if mapping_connected:
                                break
                    
                    if not mapping_connected:
                        # If not found by name, try first inputs/outputs
                        if len(mapping_node.outputs) > 0 and len(tex_node.inputs) > 0:
                            # Check that input is not already used for something else (like "Color")
                            input_socket = tex_node.inputs[0]
                            input_name = input_socket.name.lower() if hasattr(input_socket, 'name') else ""
                            if 'color' not in input_name and 'height' not in input_name:
                                node_tree.links.new(
                                    mapping_node.outputs[0],
                                    tex_node.inputs[0]
                                )
                                tex_node.label += " [UV0]"
                
                # Store special nodes for later
                if tex_type == 'color':
                    color_node = tex_node
                    tex_node.label += " [Color]"
                elif tex_type == 'ao':
                    ao_node = tex_node
                    tex_node.label += " [AO]"
                elif tex_type == 'normal':
                    normal_nodes.append(tex_node)
                    tex_node.label += " [Normal]"
                elif tex_type == 'bump':
                    bump_nodes.append(tex_node)
                    tex_node.label += " [Bump]"
                elif tex_type == 'height':
                    height_nodes.append(tex_node)
                    tex_node.label += " [Height]"
                
                # Setup for normal map (with Normalmap checkbox activated)
                if tex_type == 'normal' and self.auto_connect:
                    # Set intensity
                    bump_props = ['bump_height', 'height', 'strength', 'normal_strength']
                    for prop_name in bump_props:
                        if hasattr(tex_node, prop_name):
                            setattr(tex_node, prop_name, normal_strength)
                            break
                    
                    # Activate Normalmap checkbox on texture node
                    if hasattr(tex_node, 'normalmap'):
                        tex_node.normalmap = True
                    
                    # Connect to Bump socket of Disney node
                    socket_names_to_try = ['Bump', 'bump', 'Normal', 'normal']
                    socket_found = None
                    
                    for socket_name in socket_names_to_try:
                        if socket_name in disney_node.inputs:
                            socket_found = disney_node.inputs[socket_name]
                            break
                    
                    # If not found by name, try to find any input containing "bump" or "normal"
                    if not socket_found:
                        for input_socket in disney_node.inputs:
                            input_name = input_socket.name.lower()
                            if 'bump' in input_name or 'normal' in input_name:
                                socket_found = input_socket
                                break
                    
                    if socket_found and 'Color' in tex_node.outputs:
                        node_tree.links.new(
                            tex_node.outputs['Color'],
                            socket_found
                        )
                        tex_node.label += " →Bump"
                
                # Setup for bump map (with intermediate Bump node)
                elif tex_type == 'bump' and self.auto_connect:
                    # Create intermediate Bump node
                    try:
                        bump_node = node_tree.nodes.new(type='LuxCoreNodeTexBump')
                        bump_node.location = (tex_node.location.x + 300, tex_node.location.y)
                        bump_node.label = "Bump"
                        
                        # Set Sampling Distance to 0.001 and Bump Height to 0.01
                        if hasattr(bump_node, 'inputs'):
                            for inp in bump_node.inputs:
                                inp_name = inp.name.lower()
                                if 'sampling' in inp_name or 'distance' in inp_name:
                                    if hasattr(inp, 'default_value'):
                                        try:
                                            inp.default_value = 0.001
                                        except:
                                            pass
                                elif 'height' in inp_name or 'bump height' in inp_name:
                                    if hasattr(inp, 'default_value'):
                                        try:
                                            inp.default_value = 0.01
                                        except:
                                            pass
                        
                        # Connect texture Color output to Bump node Value input
                        if 'Color' in tex_node.outputs:
                            value_input = None
                            for inp in bump_node.inputs:
                                if 'value' in inp.name.lower():
                                    value_input = inp
                                    break
                            if value_input:
                                node_tree.links.new(tex_node.outputs['Color'], value_input)
                        
                        # Connect Bump node output to Disney Bump socket
                        socket_names_to_try = ['Bump', 'bump', 'Normal', 'normal']
                        socket_found = None
                        
                        for socket_name in socket_names_to_try:
                            if socket_name in disney_node.inputs:
                                socket_found = disney_node.inputs[socket_name]
                                break
                        
                        if not socket_found:
                            for input_socket in disney_node.inputs:
                                input_name = input_socket.name.lower()
                                if 'bump' in input_name or 'normal' in input_name:
                                    socket_found = input_socket
                                    break
                        
                        if socket_found and 'Bump' in bump_node.outputs:
                            node_tree.links.new(bump_node.outputs['Bump'], socket_found)
                            tex_node.label += " →Bump Node"
                        
                        # NOTE: 2D Mapping is connected to the TEXTURE node, not the Bump node
                        # This is already done earlier in the texture loading loop
                        
                    except Exception as e:
                        print(f"Error creating Bump node: {str(e)}")
                        # Fallback: connect directly to Disney
                        socket_found = None
                        for socket_name in ['Bump', 'bump']:
                            if socket_name in disney_node.inputs:
                                socket_found = disney_node.inputs[socket_name]
                                break
                        if socket_found and 'Color' in tex_node.outputs:
                            node_tree.links.new(tex_node.outputs['Color'], socket_found)
                
                # Setup for height/displacement map
                elif tex_type == 'height' and self.auto_connect:
                    # Check if Material Output node already exists, otherwise create it
                    if not material_output:
                        try:
                            material_output = node_tree.nodes.new(type='LuxCoreNodeMatOutput')
                            material_output.location = (disney_node.location.x + 400, disney_node.location.y)
                            material_output.label = "Material Output"
                            self.report({'INFO'}, "Created new LuxCore Material Output")
                        except Exception as e:
                            self.report({'ERROR'}, f"Cannot create LuxCore Material Output node: {str(e)}")
                            tex_node.label += " [No Output Node]"
                            continue
                    
                    # Make sure Disney node is connected to material output
                    if disney_node.outputs and 'Material' in disney_node.outputs and material_output.inputs and 'Material' in material_output.inputs:
                        disney_output = disney_node.outputs['Material']
                        material_input = material_output.inputs['Material']
                        
                        # Check if already connected
                        already_connected = False
                        for link in node_tree.links:
                            if link.to_socket == material_input and link.from_socket == disney_output:
                                already_connected = True
                                break
                        
                        if not already_connected:
                            node_tree.links.new(disney_output, material_input)
                    
                    # List of possible names for displacement node
                    displacement_node_types = [
                        'LuxCoreNodeMatHeightDisplacement',
                        'LuxCoreNodeMatDisplacement',
                        'LuxCoreNodeDisplacement',
                        'luxcore_material_height_displacement',
                        'luxcore_material_displacement',
                    ]
                    
                    displacement_node = None
                    
                    for node_type in displacement_node_types:
                        try:
                            displacement_node = node_tree.nodes.new(type=node_type)
                            break
                        except:
                            continue
                    
                    # If not found, try to search all LuxCore nodes
                    if not displacement_node:
                        for cls in bpy.types.Node.__subclasses__():
                            cls_name = cls.__name__
                            if 'LuxCore' in cls_name and ('displacement' in cls_name.lower() or 'height' in cls_name.lower()):
                                try:
                                    displacement_node = node_tree.nodes.new(type=cls_name)
                                    break
                                except:
                                    continue
                    
                    if displacement_node:
                        displacement_node.location = (disney_node.location.x - 300, tex_node.location.y)
                        displacement_node.label = "Height Displacement"
                        
                        # Set displacement height
                        height_props = ['height', 'value', 'strength', 'displacement_height']
                        for prop_name in height_props:
                            if hasattr(displacement_node, prop_name):
                                setattr(displacement_node, prop_name, displacement_height)
                                break
                        
                        # Set Scale value to 0.02
                        scale_props = ['scale', 'Scale', 'scaling', 'factor', 'multiplier', 'height_scale']
                        for prop_name in scale_props:
                            if hasattr(displacement_node, prop_name):
                                try:
                                    setattr(displacement_node, prop_name, 0.02)
                                    tex_node.label += " [Scale:0.02]"
                                    break
                                except (AttributeError, TypeError):
                                    continue
                        
                        # ENABLE SMOOTH NORMALS
                        smooth_normals_props = ['normal_smooth', 'smooth_normals', 'smooth_normal', 'normal_smoothing']
                        for prop_name in smooth_normals_props:
                            if hasattr(displacement_node, prop_name):
                                try:
                                    setattr(displacement_node, prop_name, True)
                                    tex_node.label += " [Smooth]"
                                    print(f"DEBUG: Enabled smooth normals on {displacement_node.name}")
                                    break
                                except (AttributeError, TypeError):
                                    continue
                        
                        # Connect texture to displacement node
                        if 'Color' in tex_node.outputs:
                            # Try different input names
                            input_names = ['Height', 'height', 'Displacement', 'displacement', 'Texture', 'texture', 'Input']
                            for input_name in input_names:
                                if input_name in displacement_node.inputs:
                                    node_tree.links.new(
                                        tex_node.outputs['Color'],
                                        displacement_node.inputs[input_name]
                                    )
                                    tex_node.label += " →Height"
                                    break
                            else:
                                # If not found by name, try first input
                                if len(displacement_node.inputs) > 0:
                                    node_tree.links.new(
                                        tex_node.outputs['Color'],
                                        displacement_node.inputs[0]
                                    )
                                    tex_node.label += " →Input0"
                        
                        # Crea nodo Subdivision
                        subdivision_node = None
                        try:
                            subdivision_node = node_tree.nodes.new(type='LuxCoreNodeShapeSubdiv')
                            subdivision_node.location = (displacement_node.location.x - 250, displacement_node.location.y + 150)
                            subdivision_node.label = "Subdivision"
                        except Exception as e:
                            print(f"Error creating Subdivision node: {str(e)}")
                        
                        # Collega Subdivision → Height Displacement (input Shape)
                        if subdivision_node and hasattr(displacement_node, 'inputs'):
                            shape_input_disp = None
                            for inp in displacement_node.inputs:
                                if inp.name == 'Shape' or 'shape' in inp.name.lower():
                                    shape_input_disp = inp
                                    break
                            
                            if shape_input_disp and hasattr(subdivision_node, 'outputs'):
                                shape_output_subdiv = None
                                for out in subdivision_node.outputs:
                                    if out.name == 'Shape' or 'shape' in out.name.lower():
                                        shape_output_subdiv = out
                                        break
                                if not shape_output_subdiv and len(subdivision_node.outputs) > 0:
                                    shape_output_subdiv = subdivision_node.outputs[0]
                                
                                if shape_output_subdiv:
                                    node_tree.links.new(shape_output_subdiv, shape_input_disp)
                                    tex_node.label += " +Subdiv"
                        
                        # Connect "Shape" output of Height Displacement node to Material Output
                        if material_output:
                            # Find "Shape" output in displacement node
                            if 'Shape' in displacement_node.outputs:
                                # Find "Displacement" or "Shape" input in Material Output
                                input_names = ['Displacement', 'displacement', 'Shape', 'shape']
                                connected = False
                                for input_name in input_names:
                                    if input_name in material_output.inputs:
                                        node_tree.links.new(
                                            displacement_node.outputs['Shape'],
                                            material_output.inputs[input_name]
                                        )
                                        tex_node.label += " →" + input_name
                                        connected = True
                                        break
                                if not connected:
                                    self.report({'WARNING'}, "Input for displacement not found in Material Output")
                            else:
                                # If "Shape" not found, try other outputs
                                for output_name in ['Displacement', 'displacement', 'Height', 'height', 'Vector', 'vector']:
                                    if output_name in displacement_node.outputs:
                                        # Try different inputs in Material Output
                                        for input_name in ['Displacement', 'displacement', 'Shape', 'shape']:
                                            if input_name in material_output.inputs:
                                                node_tree.links.new(
                                                    displacement_node.outputs[output_name],
                                                    material_output.inputs[input_name]
                                                )
                                                tex_node.label += f" →{input_name}"
                                                break
                                        break
                                else:
                                    self.report({'WARNING'}, "Cannot connect displacement to Material Output")
                                    tex_node.label += " [No Output]"
                        else:
                            self.report({'WARNING'}, "No Material Output found")
                            tex_node.label += " [No Output]"
                    else:
                        self.report({'ERROR'}, "Cannot create displacement node")
                        tex_node.label += " [No Disp Node]"
                
                # Setup for other textures (metallic, roughness, specular, opacity)
                elif tex_type == 'emission' and self.auto_connect:
                    # Emission requires an intermediate Emission node (LuxCoreNodeMatEmission)
                    try:
                        emission_node = node_tree.nodes.new(type='LuxCoreNodeMatEmission')
                    except Exception as e:
                        self.report({'WARNING'}, f"Cannot create Emission node: {e}")
                        tex_node.label += " [No Emission Node]"
                        continue
                    
                    emission_node.location = (disney_node.location.x - 300, tex_node.location.y)
                    emission_node.label = "Emission"
                    
                    # Connect texture to Emission node Color input
                    if 'Color' in tex_node.outputs:
                        color_input = None
                        for input_socket in emission_node.inputs:
                            if 'color' in input_socket.name.lower():
                                color_input = input_socket
                                break
                        
                        if color_input:
                            node_tree.links.new(tex_node.outputs['Color'], color_input)
                            tex_node.label += " →Emission"
                    
                    # Connect Emission node to Disney node Emission input
                    if len(emission_node.outputs) > 0:
                        emission_output = emission_node.outputs[0]
                        if 'Emission' in disney_node.inputs:
                            node_tree.links.new(emission_output, disney_node.inputs['Emission'])
                        else:
                            # Try alternative names
                            for input_socket in disney_node.inputs:
                                if 'emission' in input_socket.name.lower() or 'emit' in input_socket.name.lower():
                                    node_tree.links.new(emission_output, input_socket)
                                    break
                
                # Setup for other textures (metallic, roughness, specular, opacity)
                elif tex_type not in ['color', 'ao', 'normal', 'height', 'emission', 'orm', 'ors'] and tex_info['socket'] and tex_info['socket'] in disney_node.inputs and self.auto_connect:
                    if 'Color' in tex_node.outputs:
                        node_tree.links.new(
                            tex_node.outputs['Color'],
                            disney_node.inputs[tex_info['socket']]
                        )
                        tex_node.label += " →" + tex_info['socket']
                
                loaded_textures.append({
                    'type': tex_type,
                    'name': filename,
                    'node': tex_node
                })
                
            except Exception as e:
                self.report({'WARNING'}, f"Error loading {filename}: {str(e)}")
                continue
        
        # PHASE 2: Handling combined ORM and ORS textures
        if orm_node and self.auto_connect:
            print(f"DEBUG: Found ORM texture: {orm_node['filename']}")
            # Find corresponding texture node
            orm_tex_node = None
            for tex in loaded_textures:
                if tex['type'] == 'orm':
                    orm_tex_node = tex['node']
                    break
            
            if orm_tex_node:
                orm_ao_channel = self.setup_orm_texture(node_tree, disney_node, orm_tex_node, color_node)
                orm_tex_node.label = f"ORM: {orm_tex_node.label}"
        
        if ors_node and self.auto_connect:
            print(f"DEBUG: Found ORS texture: {ors_node['filename']}")
            # Find corresponding texture node
            ors_tex_node = None
            for tex in loaded_textures:
                if tex['type'] == 'ors':
                    ors_tex_node = tex['node']
                    break
            
            if ors_tex_node:
                ors_ao_channel = self.setup_ors_texture(node_tree, disney_node, ors_tex_node, color_node)
                ors_tex_node.label = f"ORS: {ors_tex_node.label}"
        
        # **ACTIVATE NORMALMAP CHECKBOX**
        for normal_node in normal_nodes:
            try:
                # Try different property names for Normalmap
                normalmap_props = [
                    'normalmap', 
                    'normal_map', 
                    'use_normalmap', 
                    'use_normal_map', 
                    'is_normalmap',
                    'normal',
                    'as_normal'
                ]
                
                activated = False
                for prop_name in normalmap_props:
                    if hasattr(normal_node, prop_name):
                        try:
                            setattr(normal_node, prop_name, True)
                            normal_node.label += " [Normalmap ON]"
                            activated = True
                            break
                        except:
                            continue
                
                if not activated:
                    # If property not found, try searching all node properties
                    for attr in dir(normal_node):
                        if not attr.startswith('_') and 'normal' in attr.lower():
                            try:
                                # Try to set it to True if boolean
                                value = getattr(normal_node, attr)
                                if isinstance(value, bool):
                                    setattr(normal_node, attr, True)
                                    normal_node.label += f" [{attr} ON]"
                                    break
                            except:
                                continue
            except Exception as e:
                self.report({'WARNING'}, f"Cannot activate Normalmap for {normal_node.label}: {str(e)}")
        
        # **SETUP FOR AO (AMBIENT OCCLUSION)**
        # Create node to combine Color and AO
        ao_channel = None
        if ao_node and 'Color' in ao_node.outputs:
            ao_channel = ao_node.outputs['Color']
        elif orm_ao_channel:
            ao_channel = orm_ao_channel
        elif ors_ao_channel:
            ao_channel = ors_ao_channel
        
        if self.auto_connect and color_node and ao_channel:
            try:
                # In LuxCore, we might use a Math node to multiply textures
                mix_node_types = [
                    'LuxCoreNodeTexMath',  # Most likely
                    'LuxCoreNodeMath',
                    'LuxCoreNodeTexMix',
                    'LuxCoreNodeTexMixColor',
                    'luxcore_tex_math',
                    'luxcore_tex_mix',
                ]
                
                mix_node = None
                for node_type in mix_node_types:
                    try:
                        mix_node = node_tree.nodes.new(type=node_type)
                        break
                    except:
                        continue
                
                if mix_node:
                    mix_node.location = (disney_node.location.x - 200, 
                                        color_node.location.y)
                    mix_node.label = "AO Multiply"
                    
                    # Set operation to Multiply if available
                    if hasattr(mix_node, 'operation'):
                        # Try different operation properties
                        operation_props = ['operation', 'blend_type', 'type', 'mode']
                        for prop_name in operation_props:
                            if hasattr(mix_node, prop_name):
                                try:
                                    # Set to MULTIPLY
                                    setattr(mix_node, prop_name, 'MULTIPLY')
                                    break
                                except:
                                    continue
                    
                    # Connect color and AO to Math node
                    color_connected = False
                    ao_connected = False
                    
                    for i, input_socket in enumerate(mix_node.inputs):
                        if hasattr(input_socket, 'name'):
                            input_name = input_socket.name.lower()
                            # Try different names for first input (color)
                            if not color_connected and ('value1' in input_name or 'input1' in input_name or 'a' in input_name or 'color1' in input_name or i == 0):
                                if 'Color' in color_node.outputs:
                                    node_tree.links.new(color_node.outputs['Color'], input_socket)
                                    color_connected = True
                                    color_node.label += " →Math"
                            # Try different names for second input (ao)
                            elif not ao_connected and ('value2' in input_name or 'input2' in input_name or 'b' in input_name or 'color2' in input_name or i == 1):
                                node_tree.links.new(ao_channel, input_socket)
                                ao_connected = True
                                if ao_node:
                                    ao_node.label += " →Math"
                    
                    # If not found by name, try first two inputs
                    if not color_connected and len(mix_node.inputs) > 0:
                        if 'Color' in color_node.outputs:
                            node_tree.links.new(color_node.outputs['Color'], mix_node.inputs[0])
                            color_connected = True
                            color_node.label += " →Math"
                    
                    if not ao_connected and len(mix_node.inputs) > 1:
                        node_tree.links.new(ao_channel, mix_node.inputs[1])
                        ao_connected = True
                        if ao_node:
                            ao_node.label += " →Math"
                    
                    # Connect Math node output to Disney's Base Color
                    if color_connected and ao_connected:
                        if len(mix_node.outputs) > 0:
                            output_socket = None
                            for out_socket in mix_node.outputs:
                                if hasattr(out_socket, 'name'):
                                    out_name = out_socket.name.lower()
                                    if 'value' in out_name or 'color' in out_name or 'result' in out_name:
                                        output_socket = out_socket
                                        break
                            
                            if not output_socket:
                                output_socket = mix_node.outputs[0]
                            
                            if 'Base Color' in disney_node.inputs:
                                node_tree.links.new(output_socket, disney_node.inputs['Base Color'])
                                mix_node.label += " →Base Color"
                            else:
                                self.report({'WARNING'}, "Socket 'Base Color' not found in Disney node")
                        else:
                            self.report({'WARNING'}, "Math node has no output")
                    else:
                        self.report({'WARNING'}, "Cannot connect both textures to Math node")
                
                else:
                    self.report({'WARNING'}, "Math node not available. AO connection not possible.")
                    # Connect only color texture
                    if 'Color' in color_node.outputs and 'Base Color' in disney_node.inputs:
                        node_tree.links.new(color_node.outputs['Color'], disney_node.inputs['Base Color'])
                        color_node.label += " →Base Color"
                    
            except Exception as e:
                self.report({'WARNING'}, f"Error creating Math node for AO: {str(e)}")
                # In case of error, connect only color texture
                if 'Color' in color_node.outputs and 'Base Color' in disney_node.inputs:
                    node_tree.links.new(color_node.outputs['Color'], disney_node.inputs['Base Color'])
                    color_node.label += " →Base Color"
        
        # If we only have color texture (without AO), connect it directly
        elif self.auto_connect and color_node and not ao_channel:
            if 'Color' in color_node.outputs and 'Base Color' in disney_node.inputs:
                node_tree.links.new(color_node.outputs['Color'], disney_node.inputs['Base Color'])
                color_node.label += " →Base Color"
        
        # Final report
        if loaded_textures:
            types_str = ", ".join([f"{t['type']}" for t in loaded_textures])
            
            if mapping_node:
                self.report({'INFO'}, f"Textures loaded: {len(loaded_textures)} - {types_str} - Shared UV Mapping")
            else:
                self.report({'INFO'}, f"Textures loaded: {len(loaded_textures)} - {types_str}")
            
            # Reorganize nodes
            self.organize_nodes(node_tree, disney_node, loaded_textures, mapping_node, material_output)
            
            # Zoom to view
            bpy.ops.node.view_all()
        else:
            self.report({'WARNING'}, "No textures loaded")
        
        return {'FINISHED'}
    
    def setup_orm_texture(self, node_tree, disney_node, orm_node, color_node):
        """Configure an ORM (OcclusionRoughnessMetallic) texture"""
        try:
            print(f"DEBUG: Configuring ORM texture: {orm_node.name}")
            
            # Create SplitFloat3 node
            try:
                split_node = node_tree.nodes.new(type="LuxCoreNodeTexSplitFloat3")
                split_node.location = (disney_node.location.x - 400, orm_node.location.y)
                split_node.label = "Split ORM"
            except Exception as e:
                print(f"DEBUG: Cannot create SplitFloat3 node: {str(e)}")
                return None
            
            # Connect ORM texture to SplitFloat3 node
            if hasattr(orm_node, 'outputs') and len(orm_node.outputs) > 0:
                if hasattr(split_node, 'inputs') and len(split_node.inputs) > 0:
                    # Use 'Color' output of ORM texture
                    color_output = None
                    for output in orm_node.outputs:
                        if output.name.lower() in ['color', 'image', 'value']:
                            color_output = output
                            break
                    if not color_output and len(orm_node.outputs) > 0:
                        color_output = orm_node.outputs[0]
                    
                    if color_output:
                        node_tree.links.new(color_output, split_node.inputs[0])
                        print(f"DEBUG: ORM connected to SplitFloat3")
            
            # Connect separate channels:
            # Channel G (1) -> Roughness
            # Channel B (2) -> Metallic
            # Channel R (0) -> AO (multiply with color if exists)
            
            # 1. Roughness (channel G/green) - output[1]
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 1:
                roughness_output = split_node.outputs[1]  # Channel G
                if 'Roughness' in disney_node.inputs:
                    node_tree.links.new(roughness_output, disney_node.inputs['Roughness'])
                    print(f"DEBUG: Channel G (Roughness) connected")
                else:
                    # Try to find roughness socket with alternative names
                    for input_socket in disney_node.inputs:
                        if 'rough' in input_socket.name.lower():
                            node_tree.links.new(roughness_output, input_socket)
                            print(f"DEBUG: Channel G (Roughness) connected to {input_socket.name}")
                            break
            
            # 2. Metallic (channel B/blue) - output[2]
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                metallic_output = split_node.outputs[2]  # Channel B
                if 'Metallic' in disney_node.inputs:
                    node_tree.links.new(metallic_output, disney_node.inputs['Metallic'])
                    print(f"DEBUG: Channel B (Metallic) connected")
                else:
                    # Try to find metallic socket with alternative names
                    for input_socket in disney_node.inputs:
                        if 'metal' in input_socket.name.lower():
                            node_tree.links.new(metallic_output, input_socket)
                            print(f"DEBUG: Channel B (Metallic) connected to {input_socket.name}")
                            break
            
            # 3. AO (channel R/red) - output[0] - returned for multiplication with color
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 0:
                ao_output = split_node.outputs[0]  # Channel R
                print(f"DEBUG: Channel R (AO) ready for multiplication")
                return ao_output
            
        except Exception as e:
            print(f"DEBUG: Error in ORM configuration: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def setup_ors_texture(self, node_tree, disney_node, ors_node, color_node):
        """Configure an ORS (OcclusionRoughnessSpecular) texture"""
        try:
            print(f"DEBUG: Configuring ORS texture: {ors_node.name}")
            
            # Create SplitFloat3 node
            try:
                split_node = node_tree.nodes.new(type="LuxCoreNodeTexSplitFloat3")
                split_node.location = (disney_node.location.x - 400, ors_node.location.y)
                split_node.label = "Split ORS"
            except Exception as e:
                print(f"DEBUG: Cannot create SplitFloat3 node: {str(e)}")
                return None
            
            # Connect ORS texture to SplitFloat3 node
            if hasattr(ors_node, 'outputs') and len(ors_node.outputs) > 0:
                if hasattr(split_node, 'inputs') and len(split_node.inputs) > 0:
                    # Use 'Color' output of ORS texture
                    color_output = None
                    for output in ors_node.outputs:
                        if output.name.lower() in ['color', 'image', 'value']:
                            color_output = output
                            break
                    if not color_output and len(ors_node.outputs) > 0:
                        color_output = ors_node.outputs[0]
                    
                    if color_output:
                        node_tree.links.new(color_output, split_node.inputs[0])
                        print(f"DEBUG: ORS connected to SplitFloat3")
            
            # Connect separate channels:
            # Channel G (1) -> Roughness
            # Channel B (2) -> Specular
            # Channel R (0) -> AO (multiply with color if exists)
            
            # 1. Roughness (channel G/green) - output[1]
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 1:
                roughness_output = split_node.outputs[1]  # Channel G
                if 'Roughness' in disney_node.inputs:
                    node_tree.links.new(roughness_output, disney_node.inputs['Roughness'])
                    print(f"DEBUG: Channel G (Roughness) connected")
                else:
                    # Try to find roughness socket with alternative names
                    for input_socket in disney_node.inputs:
                        if 'rough' in input_socket.name.lower():
                            node_tree.links.new(roughness_output, input_socket)
                            print(f"DEBUG: Channel G (Roughness) connected to {input_socket.name}")
                            break
            
            # 2. Specular (channel B/blue) - output[2]
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                specular_output = split_node.outputs[2]  # Channel B
                if 'Specular' in disney_node.inputs:
                    node_tree.links.new(specular_output, disney_node.inputs['Specular'])
                    print(f"DEBUG: Channel B (Specular) connected")
                else:
                    # Try to find specular socket with alternative names
                    for input_socket in disney_node.inputs:
                        if 'spec' in input_socket.name.lower():
                            node_tree.links.new(specular_output, input_socket)
                            print(f"DEBUG: Channel B (Specular) connected to {input_socket.name}")
                            break
            
            # 3. AO (channel R/red) - output[0] - returned for multiplication with color
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 0:
                ao_output = split_node.outputs[0]  # Channel R
                print(f"DEBUG: Channel R (AO) ready for multiplication")
                return ao_output
            
        except Exception as e:
            print(f"DEBUG: Error in ORS configuration: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def organize_nodes(self, node_tree, disney_node, loaded_textures, mapping_node=None, material_output=None):
        """Organize nodes for better visualization"""
        # Position Disney node in center
        disney_node.location = (0, 0)
        
        # Position mapping node if exists
        if mapping_node:
            mapping_node.location = (-900, 0)
        
        # Position textures on the left
        x_start = -600
        y_start = 300
        
        for i, tex in enumerate(loaded_textures):
            tex_node = tex['node']
            tex_node.location = (x_start, y_start - i * 280)
        
        # Position Material Output on the right
        if material_output:
            material_output.location = (400, 0)

# Context menu
class NODE_MT_luxcore_pbr_menu(Menu):
    bl_label = "LuxCore PBR"
    bl_idname = "NODE_MT_luxcore_pbr_menu"
    
    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'
        
        # Main version
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Set Disney PBR Setup",
            icon='TEXTURE'
        )
        op.auto_connect = True
        op.force_type = 'AUTO'
        
        layout.separator()
        
        # Menu with advanced options
        layout.menu("NODE_MT_luxcore_pbr_advanced", text="Advanced Options", icon='SETTINGS')

# Advanced menu
class NODE_MT_luxcore_pbr_advanced(Menu):
    bl_label = "LuxCore PBR Advanced"
    bl_idname = "NODE_MT_luxcore_pbr_advanced"
    
    def draw(self, context):
        layout = self.layout
        
        # Option with forced recognition for normal maps
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Force Normal Maps",
            icon='NORMALS_FACE'
        )
        op.force_type = 'NORMAL'
        op.auto_connect = True
        
        # Option with forced recognition for displacement
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Force Displacement",
            icon='MOD_DISPLACE'
        )
        op.force_type = 'DISPLACEMENT'
        op.auto_connect = True
        
        # Option with forced recognition for AO
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Force AO",
            icon='LIGHT_HEMI'
        )
        op.force_type = 'AO'
        op.auto_connect = True
        
        # Option with forced recognition for ORM
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Force ORM",
            icon='NODE_TEXTURE'
        )
        op.force_type = 'ORM'
        op.auto_connect = True
        
        # Option with forced recognition for ORS
        op = layout.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Force ORS",
            icon='NODE_TEXTURE'
        )
        op.force_type = 'ORS'
        op.auto_connect = True
        
        # Other forced options
        types = [
            ('COLOR', "Color/Diffuse", 'MATERIAL'),
            ('ROUGHNESS', "Roughness", 'NODE_TEXTURE'),
            ('METALLIC', "Metallic", 'SHADING_WIRE'),
            ('SPECULAR', "Specular", 'SHADING_SOLID'),
        ]
        
        for type_id, label, icon in types:
            op = layout.operator(
                LUXCORE_OT_select_pbr_textures.bl_idname,
                text=label,
                icon=icon
            )
            op.force_type = type_id
            op.auto_connect = True

# Side panel
class NODE_PT_luxcore_pbr_panel(Panel):
    bl_label = "LuxCore PBR Setup"
    bl_idname = "NODE_PT_luxcore_pbr_panel"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "LuxCore"
    
    @classmethod
    def poll(cls, context):
        return context.engine == 'LUXCORE'
    
    def draw(self, context):
        layout = self.layout
        
        # Main button
        box = layout.box()
        box.label(text="Quick Setup:", icon='LIGHT')
        
        op = box.operator(
            LUXCORE_OT_select_pbr_textures.bl_idname,
            text="Load & Connect Textures",
            icon='FILE_FOLDER'
        )
        op.auto_connect = True
        op.force_type = 'AUTO'
        
        # Info
        box = layout.box()
        box.label(text="Info:", icon='INFO')
        box.label(text="1. All textures share the same UV Mapping")
        box.label(text="2. Normal Map: 'Normalmap' checkbox automatically activated")
        box.label(text="3. Displacement: Height → Height Displacement → Shape")
        box.label(text="4. Displacement scale automatically set to 0.02")
        box.label(text="5. ORM/ORS: channels automatically split")
        box.label(text="6. AO: Color + AO → Math(Multiply) → Base Color")

# Add to context menu (only when a Disney node is selected)
def draw_luxcore_pbr_menu(self, context):
    """Show LuxCore PBR menu only when a Disney node is selected"""
    # Check if rendering engine is LuxCore
    if context.engine != 'LUXCORE':
        return
    
    # Check if we are in node editor
    if not context.space_data or not context.space_data.node_tree:
        return
    
    node_tree = context.space_data.node_tree
    active_node = node_tree.nodes.active
    
    if not active_node:
        return
    
    # Check if active node is a LuxCore Disney node
    disney_node_types = [
        'LuxCoreNodeMatDisney',
        'LuxCoreNodeMatDisney2',
        'luxcore_material_disney'
    ]
    
    if active_node.bl_idname in disney_node_types:
        layout = self.layout
        layout.separator()
        layout.menu("NODE_MT_luxcore_pbr_menu")

# Registration
def register():
    bpy.utils.register_class(LUXCORE_OT_select_pbr_textures)
    bpy.utils.register_class(NODE_MT_luxcore_pbr_menu)
    bpy.utils.register_class(NODE_MT_luxcore_pbr_advanced)
    bpy.utils.register_class(NODE_PT_luxcore_pbr_panel)
    
    bpy.types.NODE_MT_context_menu.append(draw_luxcore_pbr_menu)
    bpy.types.NODE_MT_node.append(draw_luxcore_pbr_menu)

def unregister():
    bpy.utils.unregister_class(LUXCORE_OT_select_pbr_textures)
    bpy.utils.unregister_class(NODE_MT_luxcore_pbr_menu)
    bpy.utils.unregister_class(NODE_MT_luxcore_pbr_advanced)
    bpy.utils.unregister_class(NODE_PT_luxcore_pbr_panel)
    
    bpy.types.NODE_MT_context_menu.remove(draw_luxcore_pbr_menu)
    bpy.types.NODE_MT_node.remove(draw_luxcore_pbr_menu)

if __name__ == "__main__":
    register()
