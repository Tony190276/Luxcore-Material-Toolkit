bl_info = {
    "name": "LuxCore Texture Connect",
    "author": "Tony",
    "version": (1, 3, 0),  # Separate bump from normal, added mask keyword
    "blender": (4, 2, 0),
    "location": "Node Editor > Right Click Menu on Disney node",
    "description": "Automatically connect existing textures to the Disney node",
    "category": "Material",
    "support": "COMMUNITY",
}

import bpy
import re
from bpy.types import Operator, Menu
from bpy.props import BoolProperty

class LUXCORE_OT_connect_existing_textures(Operator):
    """Automatically connect existing textures to the Disney node"""
    bl_idname = "luxcore.connect_existing_textures"
    bl_label = "Connect Textures to Disney"
    bl_options = {'REGISTER', 'UNDO'}
    
    create_uv_node: BoolProperty(
        name="Create UV Node",
        description="Create a shared 2D Mapping node for all textures",
        default=True,
    )
    
    @classmethod
    def poll(cls, context):
        if not context.space_data or not context.space_data.node_tree:
            return False
        
        node_tree = context.space_data.node_tree
        if not node_tree.nodes.active:
            return False
        
        active_node = node_tree.nodes.active
        disney_node_types = [
            'LuxCoreNodeMatDisney',
            'LuxCoreNodeMatDisney2',
            'luxcore_material_disney'
        ]
        
        return active_node.bl_idname in disney_node_types
    
    def execute(self, context):
        node_tree = context.space_data.node_tree
        disney_node = node_tree.nodes.active
        
        texture_nodes = []
        for node in node_tree.nodes:
            if node.bl_idname in ['LuxCoreNodeTexImagemap', 'LuxCoreNodeTexImage', 'ShaderNodeTexImage']:
                texture_nodes.append(node)
        
        if not texture_nodes:
            self.report({'WARNING'}, "No texture nodes found in the node tree")
            return {'CANCELLED'}
        
        normal_strength = 1.0
        displacement_height = 0.01
        
        mapping_node = None
        if self.create_uv_node:
            mapping_node = self.create_2d_mapping_node(node_tree, disney_node)
        
        material_output = self.find_or_create_material_output(node_tree, disney_node)
        
        connected_count = self.connect_textures_to_material(
            node_tree, disney_node, texture_nodes, mapping_node, material_output,
            normal_strength, displacement_height
        )
        
        if connected_count > 0:
            self.report({'INFO'}, f"Connected {connected_count} textures")
            self.organize_nodes(node_tree, disney_node, texture_nodes, mapping_node, material_output)
        else:
            self.report({'WARNING'}, "No textures were connected")
        
        return {'FINISHED'}
    
    def create_2d_mapping_node(self, node_tree, disney_node):
        """Create a shared 2D Mapping node"""
        try:
            mapping_node_types = [
                'LuxCoreNodeTexMapping2D',
                'LuxCoreNodeMapping2D',
                'luxcore_tex_mapping2d',
                'LuxCoreNodeUV',
            ]
            
            for node_type in mapping_node_types:
                try:
                    mapping_node = node_tree.nodes.new(type=node_type)
                    mapping_node.location = (disney_node.location.x - 800, disney_node.location.y)
                    mapping_node.label = "Shared UV Mapping"
                    return mapping_node
                except:
                    continue
        except Exception as e:
            print(f"Unable to create 2D Mapping node: {str(e)}")
        
        return None
    
    def find_or_create_material_output(self, node_tree, disney_node):
        """Find or create a LuxCore Material Output node"""
        for node in node_tree.nodes:
            if node.bl_idname == 'LuxCoreNodeMatOutput':
                return node
        
        try:
            material_output = node_tree.nodes.new(type='LuxCoreNodeMatOutput')
            material_output.location = (disney_node.location.x + 400, disney_node.location.y)
            material_output.label = "Material Output"
            return material_output
        except:
            return None
    
    def connect_textures_to_material(self, node_tree, material_node, texture_nodes, mapping_node, material_output,
                                    normal_strength, displacement_height):
        """Connect textures to the Disney material based on naming conventions"""
        connected_count = 0
        
        texture_mapping = {
            'orm': {
                'keywords': ['orm', 'arm', 'mro',
                           'metallicroughness', 'roughnessmetallic',
                           'occlusionroughnessmetallic', 'ambientroughnessmetallic'],
                'is_orm': True,
                'priority': 12
            },
            'ors': {
                'keywords': ['ors', 'occlusionroughnessspecular', 'roughnessspecularocclusion',
                           'specularroughnessocclusion', 'ambientroughnessspecular',
                           'occlusionroughnessgloss', 'roughnessglossocclusion'],
                'is_ors': True,
                'priority': 11
            },
            'color': {
                'keywords': ['color', 'diff', 'diffuse', 'albedo', 'basecolor', 'col', 'base'],
                'socket': 'Base Color',
                'priority': 9
            },
            'emission': {
                'keywords': ['emission', 'emit', 'emissive', 'emiss', 'glow', 'light'],
                'socket': 'Emission',
                'is_emission': True,
                'priority': 10
            },
            'normal': {
                'keywords': ['normal', 'norm', 'nrm', 'nor', 'normalmap', 'normal_map', 'normalgl', 'normaldx'],
                'socket': 'Bump',
                'is_normal': True,
                'priority': 8
            },
            'bump': {
                'keywords': ['bump', 'bmp', 'bump_map', 'bumpmap'],
                'socket': 'Bump',
                'is_bump': True,
                'priority': 7
            },
            'metallic': {
                'keywords': ['metal', 'metallic', 'metalness', 'mtl', 'met'],
                'socket': 'Metallic',
                'priority': 6
            },
            'roughness': {
                'keywords': ['rough', 'roughness', 'rgh', 'rug'],
                'socket': 'Roughness',
                'priority': 5
            },
            'specular': {
                'keywords': ['spec', 'specular', 'specularity', 'spc'],
                'socket': 'Specular',
                'priority': 4
            },
            'height': {
                'keywords': ['height', 'disp', 'displacement', 'heightmap'],
                'socket': 'Height',
                'is_height': True,
                'priority': 3
            },
            'opacity': {
                'keywords': ['opacity', 'alpha', 'transparency', 'transparent', 'mask'],
                'socket': 'Opacity',
                'priority': 2
            },
            'ao': {
                'keywords': ['ao', 'ambientocclusion', 'occlusion', 'ambient'],
                'is_ao': True,
                'priority': 1
            }
        }
        
        texture_info_list = []
        
        # Prima passata: identificare tutte le texture
        for tex_node in texture_nodes:
            node_name = tex_node.name.lower()
            image_name = ""
            
            if hasattr(tex_node, 'image') and tex_node.image:
                image_name = tex_node.image.name.lower()
            
            search_text = node_name + " " + image_name
            best_match = None
            best_priority = -1
            
            for tex_type, tex_info in texture_mapping.items():
                for keyword in tex_info['keywords']:
                    pattern = r'(^|[^a-zA-Z0-9])' + re.escape(keyword) + r'($|[^a-zA-Z0-9])'
                    if re.search(pattern, search_text, re.IGNORECASE):
                        if tex_info.get('priority', 0) > best_priority:
                            best_priority = tex_info.get('priority', 0)
                            best_match = (tex_type, tex_info)
                        break
            
            if best_match:
                tex_type, tex_info = best_match
                texture_info_list.append((tex_node, tex_type, tex_info))
                print(f"Texture identified: {tex_node.name} -> {tex_type}")
        
        texture_info_list.sort(key=lambda x: texture_mapping[x[1]].get('priority', 0), reverse=True)
        
        # Variabili per nodi speciali
        color_node = None
        ao_node = None
        normal_nodes = []
        height_nodes = []
        orm_node = None
        ors_node = None
        orm_ao_channel = None
        ors_ao_channel = None
        covered_types = set()
        
        # Seconda passata: elaborazione delle texture
        for tex_node, tex_type, tex_info in texture_info_list:
            # Controlla se questo tipo è già coperto da ORM/ORS
            if tex_type in ['metallic', 'roughness', 'ao', 'specular'] and tex_type in covered_types:
                print(f"Texture {tex_type} ({tex_node.name}) ignorata perché già coperta da ORM/ORS")
                continue
            
            try:
                if mapping_node and self.create_uv_node:
                    self.connect_mapping_to_texture(node_tree, mapping_node, tex_node)
                
                # Se è ORM, segna che copre metallic, roughness e ao
                if tex_type == 'orm':
                    covered_types.add('metallic')
                    covered_types.add('roughness')
                    covered_types.add('ao')
                    orm_node = tex_node
                    orm_ao_channel = self.setup_combined_texture(node_tree, material_node, tex_node, tex_type)
                    if orm_ao_channel:
                        connected_count += 1
                    continue
                
                # Se è ORS, segna che copre specular, roughness e ao
                elif tex_type == 'ors':
                    covered_types.add('specular')
                    covered_types.add('roughness')
                    covered_types.add('ao')
                    ors_node = tex_node
                    ors_ao_channel = self.setup_combined_texture(node_tree, material_node, tex_node, tex_type)
                    if ors_ao_channel:
                        connected_count += 1
                    continue
                
                # Aggiungi il tipo corrente ai covered_types
                covered_types.add(tex_type)
                
                if tex_type == 'color':
                    color_node = tex_node
                    tex_node.label = f"COLOR: {tex_node.label or tex_node.name}"
                
                elif tex_type == 'ao':
                    ao_node = tex_node
                    tex_node.label = f"AO: {tex_node.label or tex_node.name}"
                
                elif tex_type == 'normal':
                    normal_nodes.append(tex_node)
                    tex_node.label = f"NORMAL: {tex_node.label or tex_node.name}"
                    
                    # PRIMA: collega la normal map al socket Bump
                    if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                        # Trova il socket Bump nel nodo Disney
                        socket_found = None
                        socket_names_to_try = ['Bump', 'bump', 'Normal', 'normal']
                        
                        for socket_name in socket_names_to_try:
                            if socket_name in material_node.inputs:
                                socket_found = material_node.inputs[socket_name]
                                break
                        
                        # Se non trovato per nome, cerca qualsiasi input contenente "bump" o "normal"
                        if not socket_found:
                            for input_socket in material_node.inputs:
                                input_name = input_socket.name.lower()
                                if 'bump' in input_name or 'normal' in input_name:
                                    socket_found = input_socket
                                    break
                        
                        if socket_found:
                            # Usa l'output Color della texture
                            color_output = None
                            for output in tex_node.outputs:
                                if output.name.lower() in ['color', 'image', 'value']:
                                    color_output = output
                                    break
                            if not color_output and len(tex_node.outputs) > 0:
                                color_output = tex_node.outputs[0]
                            
                            if color_output:
                                node_tree.links.new(color_output, socket_found)
                                connected_count += 1
                                tex_node.label += " →Bump"
                                
                                # SOLO DOPO aver collegato: attiva la checkbox Normalmap
                                self.activate_normal_map(tex_node)
                
                elif tex_type == 'bump':
                    # Bump map richiede un nodo intermedio LuxCoreNodeTexBump
                    if self.setup_bump(node_tree, material_node, tex_node, mapping_node):
                        connected_count += 1
                        tex_node.label = f"BUMP: {tex_node.label or tex_node.name}"
                
                elif tex_type == 'height':
                    height_nodes.append(tex_node)
                    self.setup_displacement(node_tree, material_node, tex_node, material_output, displacement_height)
                    connected_count += 1
                    tex_node.label = f"HEIGHT: {tex_node.label or tex_node.name}"
                
                elif tex_type == 'emission':
                    # Emission richiede un nodo intermedio
                    if self.setup_emission(node_tree, material_node, tex_node):
                        connected_count += 1
                        tex_node.label = f"EMISSION: {tex_node.label or tex_node.name}"
                
                elif tex_type not in ['color', 'ao', 'normal', 'bump', 'height', 'emission'] and tex_info['socket'] and tex_info['socket'] in material_node.inputs:
                    if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                        # Usa l'output Color della texture
                        color_output = None
                        for output in tex_node.outputs:
                            if output.name.lower() in ['color', 'image', 'value']:
                                color_output = output
                                break
                        if not color_output and len(tex_node.outputs) > 0:
                            color_output = tex_node.outputs[0]
                        
                        if color_output:
                            node_tree.links.new(color_output, material_node.inputs[tex_info['socket']])
                            connected_count += 1
                            tex_node.label = f"{tex_type.upper()}: {tex_node.label or tex_node.name} →{tex_info['socket']}"
                
            except Exception as e:
                print(f"Error connecting texture {tex_node.name}: {e}")
        
        # Setup per AO (Ambient Occlusion)
        ao_channel = None
        if ao_node and hasattr(ao_node, 'outputs') and len(ao_node.outputs) > 0:
            # Usa l'output Color della texture AO
            for output in ao_node.outputs:
                if output.name.lower() in ['color', 'image', 'value']:
                    ao_channel = output
                    break
            if not ao_channel and len(ao_node.outputs) > 0:
                ao_channel = ao_node.outputs[0]
        
        elif orm_ao_channel:
            ao_channel = orm_ao_channel
        elif ors_ao_channel:
            ao_channel = ors_ao_channel
        
        # Combina Color e AO
        if color_node and ao_channel:
            self.setup_ao_multiply(node_tree, material_node, color_node, ao_channel, ao_node or orm_node or ors_node)
            connected_count += 1
        elif color_node:
            # Collega solo la texture di colore
            if hasattr(color_node, 'outputs') and len(color_node.outputs) > 0:
                color_output = None
                for output in color_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output and len(color_node.outputs) > 0:
                    color_output = color_node.outputs[0]
                
                if color_output and 'Base Color' in material_node.inputs:
                    node_tree.links.new(color_output, material_node.inputs['Base Color'])
                    color_node.label += " →Base Color"
                    connected_count += 1
        
        return connected_count
    
    def connect_mapping_to_texture(self, node_tree, mapping_node, tex_node):
        """Connect shared UV Mapping to a texture node"""
        try:
            if hasattr(mapping_node, 'outputs') and len(mapping_node.outputs) > 0:
                if hasattr(tex_node, 'inputs') and len(tex_node.inputs) > 0:
                    # Cerca input di mapping
                    mapping_inputs = ['2D Mapping', 'Mapping', 'UV', 'UV Map', 'UVs', 'Vector']
                    
                    for input_socket in tex_node.inputs:
                        input_name = input_socket.name.lower()
                        for map_input in mapping_inputs:
                            if map_input.lower() in input_name:
                                # Cerca output di mapping
                                mapping_outputs = ['2D Mapping', 'Mapping', 'UV', 'Vector', 'Output']
                                for output_name in mapping_outputs:
                                    if output_name in mapping_node.outputs:
                                        node_tree.links.new(
                                            mapping_node.outputs[output_name],
                                            input_socket
                                        )
                                        tex_node.label = (tex_node.label or tex_node.name) + " [UV]"
                                        return True
                    
                    # Se non trovato per nome, prova il primo input
                    if len(mapping_node.outputs) > 0 and len(tex_node.inputs) > 0:
                        input_socket = tex_node.inputs[0]
                        input_name = input_socket.name.lower() if hasattr(input_socket, 'name') else ""
                        if 'color' not in input_name and 'height' not in input_name:
                            node_tree.links.new(mapping_node.outputs[0], input_socket)
                            tex_node.label = (tex_node.label or tex_node.name) + " [UV0]"
                            return True
        except Exception as e:
            print(f"Error connecting mapping: {str(e)}")
        
        return False
    
    def activate_normal_map(self, tex_node):
        """Activate normal map checkbox - ONLY after connecting to Bump socket"""
        try:
            # Attiva checkbox Normalmap - ORDINE DI PRIORITÀ CORRETTO
            normalmap_props = [
                'is_normal_map',  # PRIORITÀ MASSIMA
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
                if hasattr(tex_node, prop_name):
                    try:
                        # Controlla se è già True
                        current_value = getattr(tex_node, prop_name)
                        
                        if current_value == True:
                            print(f"Normalmap già attiva per {tex_node.name}: {prop_name} = {current_value}")
                            tex_node.label += " [Normalmap ON]"
                            activated = True
                            break
                        
                        # Prova a impostare a True
                        setattr(tex_node, prop_name, True)
                        print(f"Attivata normalmap per {tex_node.name}: {prop_name} = True")
                        tex_node.label += f" [{prop_name}=True]"
                        activated = True
                        break
                    except Exception as e:
                        print(f"Impossibile impostare {prop_name} su True per {tex_node.name}: {e}")
                        continue
            
            if not activated:
                print(f"Nessuna proprietà normalmap trovata per {tex_node.name}")
                tex_node.label += " [No Normalmap Prop]"
                        
        except Exception as e:
            print(f"Error setting normal map properties: {e}")
    
    def setup_emission(self, node_tree, material_node, tex_node):
        """Setup Emission texture through an intermediate Emission node"""
        try:
            # Create Emission node (LuxCoreNodeMatEmission)
            try:
                emission_node = node_tree.nodes.new(type='LuxCoreNodeMatEmission')
            except Exception as e:
                print(f"Cannot create Emission node: {e}")
                return False
            
            # Position Emission node between texture and Disney node
            emission_node.location = (material_node.location.x - 300, tex_node.location.y)
            emission_node.label = "Emission"
            
            # Connect texture to Color pin of Emission node
            if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                color_output = None
                for output in tex_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output:
                    color_output = tex_node.outputs[0]
                
                if color_output and hasattr(emission_node, 'inputs'):
                    # Find Color input in Emission node
                    color_input = None
                    for input_socket in emission_node.inputs:
                        if 'color' in input_socket.name.lower():
                            color_input = input_socket
                            break
                    
                    if color_input:
                        node_tree.links.new(color_output, color_input)
                        
                        # Set sRGB gamma for emission (it's a color)
                        if hasattr(tex_node, 'color_space'):
                            tex_node.color_space = 'sRGB'
                    else:
                        print("Color input not found in Emission node")
                        return False
            
            # Connect Emission node to Emission pin of Disney node
            if hasattr(emission_node, 'outputs') and len(emission_node.outputs) > 0:
                emission_output = emission_node.outputs[0]
                
                # Find Emission input in Disney node
                if 'Emission' in material_node.inputs:
                    node_tree.links.new(emission_output, material_node.inputs['Emission'])
                    return True
                else:
                    # Try alternative names
                    for input_socket in material_node.inputs:
                        if 'emission' in input_socket.name.lower() or 'emit' in input_socket.name.lower():
                            node_tree.links.new(emission_output, input_socket)
                            return True
                    
                    print("Emission input not found in Disney node")
                    return False
            
        except Exception as e:
            print(f"Error setting up emission: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def setup_bump(self, node_tree, material_node, tex_node, mapping_node=None):
        """Setup Bump texture through an intermediate Bump node (LuxCoreNodeTexBump)"""
        try:
            # Create Bump node
            try:
                bump_node = node_tree.nodes.new(type='LuxCoreNodeTexBump')
            except Exception as e:
                print(f"Cannot create Bump node: {e}")
                return False
            
            # Position Bump node between texture and material node
            bump_node.location = (material_node.location.x - 300, tex_node.location.y)
            bump_node.label = "Bump"
            
            # Set Sampling Distance to 0.001 and Bump Height to 0.01
            if hasattr(bump_node, 'inputs'):
                for inp in bump_node.inputs:
                    inp_name = inp.name.lower()
                    if 'sampling' in inp_name or 'distance' in inp_name:
                        if hasattr(inp, 'default_value'):
                            try:
                                inp.default_value = 0.001
                                print(f"Set Sampling Distance to 0.001 on input: {inp.name}")
                            except:
                                pass
                    elif 'height' in inp_name or 'bump height' in inp_name:
                        if hasattr(inp, 'default_value'):
                            try:
                                inp.default_value = 0.01
                                print(f"Set Bump Height to 0.01 on input: {inp.name}")
                            except:
                                pass
            
            # Connect texture Color output to Bump node Value input
            if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                color_output = None
                for output in tex_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output:
                    color_output = tex_node.outputs[0]
                
                if color_output and hasattr(bump_node, 'inputs'):
                    # Find Value input in Bump node
                    value_input = None
                    for inp in bump_node.inputs:
                        if 'value' in inp.name.lower():
                            value_input = inp
                            break
                    
                    if value_input:
                        node_tree.links.new(color_output, value_input)
                        print(f"Connected texture to Bump node Value input")
                    else:
                        print("Value input not found in Bump node")
                        return False
            
            # NOTE: 2D Mapping should be connected to the TEXTURE node, not the Bump node
            # The mapping is already connected to the texture before calling setup_bump
            
            # Connect Bump node output to Disney Bump socket
            if hasattr(bump_node, 'outputs') and len(bump_node.outputs) > 0:
                bump_output = None
                for output in bump_node.outputs:
                    if 'bump' in output.name.lower():
                        bump_output = output
                        break
                if not bump_output:
                    bump_output = bump_node.outputs[0]
                
                # Find Bump input in material node
                socket_names_to_try = ['Bump', 'bump', 'Normal', 'normal']
                socket_found = None
                
                for socket_name in socket_names_to_try:
                    if socket_name in material_node.inputs:
                        socket_found = material_node.inputs[socket_name]
                        break
                
                if not socket_found:
                    for input_socket in material_node.inputs:
                        if 'bump' in input_socket.name.lower() or 'normal' in input_socket.name.lower():
                            socket_found = input_socket
                            break
                
                if socket_found and bump_output:
                    node_tree.links.new(bump_output, socket_found)
                    tex_node.label += " →Bump Node"
                    print(f"Connected Bump node to {socket_found.name}")
                    return True
                else:
                    print("Bump input not found in material node")
                    return False
            
        except Exception as e:
            print(f"Error setting up bump: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def setup_combined_texture(self, node_tree, material_node, combined_node, tex_type):
        """Configure an ORM or ORS combined texture with channel splitting, returns AO output"""
        try:
            print(f"DEBUG: Configuring {tex_type} texture: {combined_node.name}")
            
            try:
                split_node = node_tree.nodes.new(type="LuxCoreNodeTexSplitFloat3")
                split_node.location = (material_node.location.x - 400, combined_node.location.y)
                split_node.label = f"Split {tex_type.upper()}"
            except Exception as e:
                print(f"DEBUG: Cannot create SplitFloat3 node: {str(e)}")
                return None
            
            # Connect combined texture to SplitFloat3 node
            if hasattr(combined_node, 'outputs') and len(combined_node.outputs) > 0:
                if hasattr(split_node, 'inputs') and len(split_node.inputs) > 0:
                    color_output = None
                    for output in combined_node.outputs:
                        if output.name.lower() in ['color', 'image', 'value']:
                            color_output = output
                            break
                    if not color_output and len(combined_node.outputs) > 0:
                        color_output = combined_node.outputs[0]
                    
                    if color_output:
                        node_tree.links.new(color_output, split_node.inputs[0])
                        print(f"DEBUG: {tex_type.upper()} connected to SplitFloat3")
            
            # Set texture to Non-Color
            if hasattr(combined_node, 'color_space'):
                combined_node.color_space = 'Non-Color'
            elif hasattr(combined_node, 'gamma'):
                combined_node.gamma = 1.0
            
            # Connect separate channels:
            # Channel G (1) -> Roughness (for both ORM and ORS)
            # Channel B (2) -> Metallic (for ORM) or Specular (for ORS)
            # Channel R (0) -> AO (return for multiplication with color)
            
            # 1. Roughness (channel G/green) - output[1]
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 1:
                roughness_output = split_node.outputs[1]  # Channel G
                if 'Roughness' in material_node.inputs:
                    node_tree.links.new(roughness_output, material_node.inputs['Roughness'])
                    print(f"DEBUG: Channel G (Roughness) connected")
                else:
                    # Try to find roughness socket with alternative names
                    for input_socket in material_node.inputs:
                        if 'rough' in input_socket.name.lower():
                            node_tree.links.new(roughness_output, input_socket)
                            print(f"DEBUG: Channel G (Roughness) connected to {input_socket.name}")
                            break
            
            # 2. Metallic (channel B/blue) - output[2] for ORM
            if tex_type == 'orm':
                if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                    metallic_output = split_node.outputs[2]  # Channel B
                    if 'Metallic' in material_node.inputs:
                        node_tree.links.new(metallic_output, material_node.inputs['Metallic'])
                        print(f"DEBUG: Channel B (Metallic) connected")
                    else:
                        # Try to find metallic socket with alternative names
                        for input_socket in material_node.inputs:
                            if 'metal' in input_socket.name.lower():
                                node_tree.links.new(metallic_output, input_socket)
                                print(f"DEBUG: Channel B (Metallic) connected to {input_socket.name}")
                                break
            
            # 3. Specular (channel B/blue) - output[2] for ORS
            elif tex_type == 'ors':
                if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                    specular_output = split_node.outputs[2]  # Channel B
                    if 'Specular' in material_node.inputs:
                        node_tree.links.new(specular_output, material_node.inputs['Specular'])
                        print(f"DEBUG: Channel B (Specular) connected")
                    else:
                        # Try to find specular socket with alternative names
                        for input_socket in material_node.inputs:
                            if 'spec' in input_socket.name.lower():
                                node_tree.links.new(specular_output, input_socket)
                                print(f"DEBUG: Channel B (Specular) connected to {input_socket.name}")
                                break
            
            # 4. AO (channel R/red) - output[0] - returned for multiplication with color
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 0:
                ao_output = split_node.outputs[0]  # Channel R
                print(f"DEBUG: Channel R (AO) ready for multiplication")
                
                # Label the combined texture node
                combined_node.label = f"{tex_type.upper()}: {combined_node.label or combined_node.name}"
                
                return ao_output
            
        except Exception as e:
            print(f"DEBUG: Error in {tex_type} configuration: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def setup_displacement(self, node_tree, material_node, height_node, material_output, height):
        """Setup height/displacement texture with Height Displacement node"""
        if not material_output:
            return
        
        try:
            displacement_node_types = [
                'LuxCoreNodeShapeHeightDisplacement',
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
            
            if not displacement_node:
                return
            
            displacement_node.location = (material_node.location.x - 300, height_node.location.y)
            displacement_node.label = "Height Displacement"
            
            if hasattr(displacement_node, 'height'):
                displacement_node.height = height
            elif hasattr(displacement_node, 'value'):
                displacement_node.value = height
            
            if hasattr(displacement_node, 'scale'):
                displacement_node.scale = 0.02
                height_node.label = (height_node.label or height_node.name) + " [Scale:0.02]"
            
            # Abilita smooth normals
            smooth_normals_props = ['normal_smooth', 'smooth_normals', 'smooth_normal', 'normal_smoothing']
            for prop_name in smooth_normals_props:
                if hasattr(displacement_node, prop_name):
                    try:
                        setattr(displacement_node, prop_name, True)
                        height_node.label += " [Smooth]"
                        break
                    except:
                        continue
            
            if hasattr(height_node, 'outputs') and len(height_node.outputs) > 0:
                if hasattr(displacement_node, 'inputs') and len(displacement_node.inputs) > 0:
                    # Trova input Height
                    input_names = ['Height', 'height', 'Displacement', 'displacement', 'Texture', 'texture']
                    for input_name in input_names:
                        if input_name in displacement_node.inputs:
                            color_output = None
                            for output in height_node.outputs:
                                if output.name.lower() in ['color', 'image', 'value']:
                                    color_output = output
                                    break
                            if not color_output and len(height_node.outputs) > 0:
                                color_output = height_node.outputs[0]
                            
                            if color_output:
                                node_tree.links.new(color_output, displacement_node.inputs[input_name])
                                height_node.label += " →Height"
                                break
            
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
                        subdivision_node.label += " →Shape"
            
            if hasattr(displacement_node, 'outputs') and len(displacement_node.outputs) > 0:
                # Collega Height Displacement → Material Output
                if hasattr(material_output, 'inputs') and len(material_output.inputs) > 0:
                    # Trova input Shape/Displacement nel Material Output
                    input_names = ['Displacement', 'displacement', 'Shape', 'shape']
                    for input_name in input_names:
                        if input_name in material_output.inputs:
                            # Trova output Shape nel displacement node
                            if 'Shape' in displacement_node.outputs:
                                node_tree.links.new(displacement_node.outputs['Shape'], material_output.inputs[input_name])
                                displacement_node.label += " →" + input_name
                                break
                            else:
                                # Usa il primo output
                                if len(displacement_node.outputs) > 0:
                                    node_tree.links.new(displacement_node.outputs[0], material_output.inputs[input_name])
                                    displacement_node.label += " →" + input_name
                                    break
            
        except Exception as e:
            print(f"Error setting up displacement: {str(e)}")
    
    def setup_ao_multiply(self, node_tree, material_node, color_node, ao_channel, ao_node):
        """Create Math node to multiply Color with AO"""
        try:
            # Crea nodo Math per moltiplicazione
            math_node_types = [
                'LuxCoreNodeTexMath',
                'LuxCoreNodeMath',
                'LuxCoreNodeTexMix',
                'LuxCoreNodeTexMixColor',
                'luxcore_tex_math',
                'luxcore_tex_mix',
            ]
            
            math_node = None
            for node_type in math_node_types:
                try:
                    math_node = node_tree.nodes.new(type=node_type)
                    break
                except:
                    continue
            
            if math_node:
                math_node.location = (material_node.location.x - 200, color_node.location.y)
                math_node.label = "AO Multiply"
                
                # Imposta operazione a Multiply se disponibile
                if hasattr(math_node, 'operation'):
                    operation_props = ['operation', 'blend_type', 'type', 'mode']
                    for prop_name in operation_props:
                        if hasattr(math_node, prop_name):
                            try:
                                setattr(math_node, prop_name, 'MULTIPLY')
                                break
                            except:
                                continue
                
                # Collega color e AO al nodo Math
                color_connected = False
                ao_connected = False
                
                for i, input_socket in enumerate(math_node.inputs):
                    if hasattr(input_socket, 'name'):
                        input_name = input_socket.name.lower()
                        # Primo input (color)
                        if not color_connected and ('value1' in input_name or 'input1' in input_name or 'a' in input_name or 'color1' in input_name or i == 0):
                            color_output = None
                            for output in color_node.outputs:
                                if output.name.lower() in ['color', 'image', 'value']:
                                    color_output = output
                                    break
                            if not color_output and len(color_node.outputs) > 0:
                                color_output = color_node.outputs[0]
                            
                            if color_output:
                                node_tree.links.new(color_output, input_socket)
                                color_connected = True
                                color_node.label += " →Math"
                        # Secondo input (ao)
                        elif not ao_connected and ('value2' in input_name or 'input2' in input_name or 'b' in input_name or 'color2' in input_name or i == 1):
                            node_tree.links.new(ao_channel, input_socket)
                            ao_connected = True
                            if ao_node:
                                ao_node.label += " →Math"
                
                # Se non trovato per nome, usa i primi due input
                if not color_connected and len(math_node.inputs) > 0:
                    color_output = None
                    for output in color_node.outputs:
                        if output.name.lower() in ['color', 'image', 'value']:
                            color_output = output
                            break
                    if not color_output and len(color_node.outputs) > 0:
                        color_output = color_node.outputs[0]
                    
                    if color_output:
                        node_tree.links.new(color_output, math_node.inputs[0])
                        color_connected = True
                        color_node.label += " →Math"
                
                if not ao_connected and len(math_node.inputs) > 1:
                    node_tree.links.new(ao_channel, math_node.inputs[1])
                    ao_connected = True
                    if ao_node:
                        ao_node.label += " →Math"
                
                # Collega output Math a Base Color del Disney
                if color_connected and ao_connected:
                    if len(math_node.outputs) > 0:
                        output_socket = None
                        for out_socket in math_node.outputs:
                            if hasattr(out_socket, 'name'):
                                out_name = out_socket.name.lower()
                                if 'value' in out_name or 'color' in out_name or 'result' in out_name:
                                    output_socket = out_socket
                                    break
                        
                        if not output_socket:
                            output_socket = math_node.outputs[0]
                        
                        if 'Base Color' in material_node.inputs:
                            node_tree.links.new(output_socket, material_node.inputs['Base Color'])
                            math_node.label += " →Base Color"
                        else:
                            print("Socket 'Base Color' not found in Disney node")
                    else:
                        print("Math node has no output")
                else:
                    print("Cannot connect both textures to Math node")
            
            else:
                print("Math node not available. AO connection not possible.")
                # Collega solo la texture di colore
                color_output = None
                for output in color_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output and len(color_node.outputs) > 0:
                    color_output = color_node.outputs[0]
                
                if color_output and 'Base Color' in material_node.inputs:
                    node_tree.links.new(color_output, material_node.inputs['Base Color'])
                    color_node.label += " →Base Color"
                    
        except Exception as e:
            print(f"Error creating Math node for AO: {str(e)}")
            # In caso di errore, collega solo la texture di colore
            color_output = None
            for output in color_node.outputs:
                if output.name.lower() in ['color', 'image', 'value']:
                    color_output = output
                    break
            if not color_output and len(color_node.outputs) > 0:
                color_output = color_node.outputs[0]
            
            if color_output and 'Base Color' in material_node.inputs:
                node_tree.links.new(color_output, material_node.inputs['Base Color'])
                color_node.label += " →Base Color"
    
    def organize_nodes(self, node_tree, material_node, texture_nodes, mapping_node, material_output):
        """Organize nodes in a clean layout"""
        material_node.location = (0, 0)
        
        if mapping_node:
            mapping_node.location = (-800, 0)
        
        x_start = -600
        y_start = 300
        
        for i, tex_node in enumerate(texture_nodes):
            tex_node.location = (x_start, y_start - i * 120)
        
        if material_output:
            material_output.location = (400, 0)
        
        # Auto zoom to fit all nodes
        for area in bpy.context.screen.areas:
            if area.type == 'NODE_EDITOR':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with bpy.context.temp_override(area=area, region=region):
                            bpy.ops.node.view_all()

def draw_luxcore_connect_menu(self, context):
    if not context.space_data or not context.space_data.node_tree:
        return
    
    node_tree = context.space_data.node_tree
    active_node = node_tree.nodes.active
    
    if not active_node:
        return
    
    disney_node_types = [
        'LuxCoreNodeMatDisney',
        'LuxCoreNodeMatDisney2',
        'luxcore_material_disney'
    ]
    
    if active_node.bl_idname in disney_node_types:
        layout = self.layout
        layout.separator()
        layout.operator(
            LUXCORE_OT_connect_existing_textures.bl_idname,
            text="Connect Textures to Disney",
            icon='LINKED'
        )

def register():
    bpy.utils.register_class(LUXCORE_OT_connect_existing_textures)
    
    bpy.types.NODE_MT_context_menu.append(draw_luxcore_connect_menu)
    bpy.types.NODE_MT_node.append(draw_luxcore_connect_menu)

def unregister():
    bpy.utils.unregister_class(LUXCORE_OT_connect_existing_textures)
    
    bpy.types.NODE_MT_context_menu.remove(draw_luxcore_connect_menu)
    bpy.types.NODE_MT_node.remove(draw_luxcore_connect_menu)

if __name__ == "__main__":
    register()
