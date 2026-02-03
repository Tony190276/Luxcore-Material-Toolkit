bl_info = {
    "name": "LuxCore Connect Selected Texture",
    "author": "Tony",
    "version": (1, 2, 0),  # Added Bump and Opacity types
    "blender": (4, 2, 0),
    "location": "Node Editor > Right Click Menu on Texture node",
    "description": "Connect selected texture to Disney node as specific type",
    "category": "Material",
    "support": "COMMUNITY",
}

import bpy
import re
from bpy.types import Operator, Menu
from bpy.props import StringProperty, EnumProperty

class LUXCORE_OT_connect_selected_texture(Operator):
    """Connect selected texture to Disney node as specific type"""
    bl_idname = "luxcore.connect_selected_texture"
    bl_label = "Connect Texture as"
    bl_options = {'REGISTER', 'UNDO'}
    
    texture_type: EnumProperty(
        name="Texture Type",
        items=[
            ('COLOR', "Color", "Color texture"),
            ('ROUGHNESS', "Roughness", "Roughness texture"),
            ('NORMAL', "Normal", "Normal map texture"),
            ('BUMP', "Bump", "Bump map texture (uses intermediate Bump node)"),
            ('SPECULAR', "Specular", "Specular texture"),
            ('METALLIC', "Metallic", "Metallic texture"),
            ('OCCLUSION', "Occlusion", "Ambient occlusion texture"),
            ('HEIGHT', "Height", "Displacement/height texture"),
            ('OPACITY', "Opacity/Mask", "Opacity/Mask texture"),
            ('EMISSION', "Emission", "Emission/Emissive texture"),
            ('ORM', "ORM", "ORM (OcclusionRoughnessMetallic) texture"),
            ('ORS', "ORS", "ORS (OcclusionRoughnessSpecular) texture"),
        ],
        default='COLOR'
    )
    
    @classmethod
    def poll(cls, context):
        if not context.space_data or not context.space_data.node_tree:
            return False
        
        node_tree = context.space_data.node_tree
        if not node_tree.nodes.active:
            return False
        
        active_node = node_tree.nodes.active
        texture_node_types = [
            'LuxCoreNodeTexImagemap',
            'LuxCoreNodeTexImage',
            'ShaderNodeTexImage'
        ]
        
        return active_node.bl_idname in texture_node_types
    
    def execute(self, context):
        node_tree = context.space_data.node_tree
        texture_node = node_tree.nodes.active
        
        disney_node = None
        for node in node_tree.nodes:
            if node.bl_idname in ['LuxCoreNodeMatDisney', 'LuxCoreNodeMatDisney2', 'luxcore_material_disney']:
                disney_node = node
                break
        
        if not disney_node:
            self.report({'ERROR'}, "No Disney node found in the tree")
            return {'CANCELLED'}
        
        material_output = None
        for node in node_tree.nodes:
            if node.bl_idname == 'LuxCoreNodeMatOutput':
                material_output = node
                break
        
        normal_strength = 1.0
        displacement_height = 0.01
        
        success = False
        
        if self.texture_type == 'COLOR':
            success = self.connect_color(node_tree, texture_node, disney_node)
        elif self.texture_type == 'ROUGHNESS':
            success = self.connect_roughness(node_tree, texture_node, disney_node)
        elif self.texture_type == 'NORMAL':
            success = self.connect_normal(node_tree, texture_node, disney_node, normal_strength)
        elif self.texture_type == 'BUMP':
            success = self.connect_bump(node_tree, texture_node, disney_node)
        elif self.texture_type == 'SPECULAR':
            success = self.connect_specular(node_tree, texture_node, disney_node)
        elif self.texture_type == 'METALLIC':
            success = self.connect_metallic(node_tree, texture_node, disney_node)
        elif self.texture_type == 'OCCLUSION':
            success = self.connect_occlusion(node_tree, texture_node, disney_node)
        elif self.texture_type == 'HEIGHT':
            success = self.connect_height(node_tree, texture_node, disney_node, material_output, displacement_height)
        elif self.texture_type == 'OPACITY':
            success = self.connect_opacity(node_tree, texture_node, disney_node)
        elif self.texture_type == 'EMISSION':
            success = self.connect_emission(node_tree, texture_node, disney_node)
        elif self.texture_type == 'ORM':
            success = self.connect_orm(node_tree, texture_node, disney_node)
        elif self.texture_type == 'ORS':
            success = self.connect_ors(node_tree, texture_node, disney_node)
        
        if success:
            self.report({'INFO'}, f"Texture connected as {self.texture_type}")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Cannot connect texture as {self.texture_type}")
            return {'CANCELLED'}
    
    def connect_color(self, node_tree, texture_node, disney_node):
        if 'Base Color' in disney_node.inputs and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], disney_node.inputs['Base Color'])
                texture_node.label = f"COLOR: {texture_node.label or texture_node.name}"
                return True
        return False
    
    def connect_roughness(self, node_tree, texture_node, disney_node):
        if 'Roughness' in disney_node.inputs and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], disney_node.inputs['Roughness'])
                texture_node.label = f"ROUGHNESS: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                return True
        return False
    
    def connect_normal(self, node_tree, texture_node, disney_node, normal_strength):
        socket_names_to_try = ['Bump', 'bump', 'Normal', 'normal']
        socket_found = None
        
        for socket_name in socket_names_to_try:
            if socket_name in disney_node.inputs:
                socket_found = disney_node.inputs[socket_name]
                break
        
        if not socket_found:
            for input_socket in disney_node.inputs:
                if 'bump' in input_socket.name.lower() or 'normal' in input_socket.name.lower():
                    socket_found = input_socket
                    break
        
        if socket_found and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                if texture_node.bl_idname == 'ShaderNodeTexImage':
                    try:
                        normal_map_node = node_tree.nodes.new('ShaderNodeNormalMap')
                        normal_map_node.location = (texture_node.location.x + 200, texture_node.location.y)
                        node_tree.links.new(texture_node.outputs['Color'], normal_map_node.inputs['Color'])
                        node_tree.links.new(normal_map_node.outputs['Normal'], socket_found)
                        normal_map_node.inputs['Strength'].default_value = normal_strength
                    except Exception as e:
                        node_tree.links.new(texture_node.outputs['Color'], socket_found)
                else:
                    node_tree.links.new(texture_node.outputs['Color'], socket_found)
                
                texture_node.label = f"NORMAL: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                self.activate_normal_map(texture_node, normal_strength)
                
                return True
        return False
    
    def connect_bump(self, node_tree, texture_node, disney_node):
        """Connect bump texture through intermediate Bump node"""
        try:
            # Create Bump node
            bump_node = node_tree.nodes.new(type='LuxCoreNodeTexBump')
            bump_node.location = (texture_node.location.x + 300, texture_node.location.y)
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
            
            # Connect texture to Bump node Value input
            if hasattr(texture_node, 'outputs') and 'Color' in texture_node.outputs:
                value_input = None
                for inp in bump_node.inputs:
                    if 'value' in inp.name.lower():
                        value_input = inp
                        break
                
                if value_input:
                    node_tree.links.new(texture_node.outputs['Color'], value_input)
            
            # Connect Bump node to Disney Bump socket
            socket_found = None
            for socket_name in ['Bump', 'bump', 'Normal', 'normal']:
                if socket_name in disney_node.inputs:
                    socket_found = disney_node.inputs[socket_name]
                    break
            
            if not socket_found:
                for input_socket in disney_node.inputs:
                    if 'bump' in input_socket.name.lower() or 'normal' in input_socket.name.lower():
                        socket_found = input_socket
                        break
            
            if socket_found and 'Bump' in bump_node.outputs:
                node_tree.links.new(bump_node.outputs['Bump'], socket_found)
                texture_node.label = f"BUMP: {texture_node.label or texture_node.name}"
                
                # Set Non-Color
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                return True
            
        except Exception as e:
            print(f"Error connecting bump: {e}")
        
        return False
    
    def connect_specular(self, node_tree, texture_node, disney_node):
        if 'Specular' in disney_node.inputs and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], disney_node.inputs['Specular'])
                texture_node.label = f"SPECULAR: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                return True
        return False
    
    def connect_metallic(self, node_tree, texture_node, disney_node):
        if 'Metallic' in disney_node.inputs and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], disney_node.inputs['Metallic'])
                texture_node.label = f"METALLIC: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                return True
        return False
    
    def connect_occlusion(self, node_tree, texture_node, disney_node):
        """Collega la texture di Occlusione moltiplicandola con la Color texture esistente"""
        color_input = disney_node.inputs.get('Base Color')
        if not color_input:
            self.report({'WARNING'}, "No Base Color input found on Disney node")
            return False
        
        try:
            # 1. Trova il collegamento esistente del colore
            existing_color_link = None
            color_source_node = None
            for link in node_tree.links:
                if link.to_socket == color_input:
                    existing_color_link = link
                    color_source_node = link.from_node
                    break
            
            if not existing_color_link:
                self.report({'ERROR'}, "Connect a Color Texture first")
                return False
            
            # 2. Crea nodo Math per moltiplicazione (usando solo nodi LuxCore)
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
            
            if not math_node:
                self.report({'ERROR'}, "Cannot create Math node for AO multiply")
                return False
            
            math_node.location = (disney_node.location.x - 250, texture_node.location.y)
            math_node.label = "AO Multiply"
            
            # 3. Configura il nodo Math per operazione MULTIPLY
            operation_props = ['operation', 'blend_type', 'type', 'mode']
            for prop_name in operation_props:
                if hasattr(math_node, prop_name):
                    try:
                        setattr(math_node, prop_name, 'MULTIPLY')
                        break
                    except:
                        continue
            
            # 4. Imposta la texture AO come Non-Color
            if hasattr(texture_node, 'color_space'):
                texture_node.color_space = 'Non-Color'
            elif hasattr(texture_node, 'gamma'):
                texture_node.gamma = 1.0
            
            texture_node.label = f"AO: {texture_node.label or texture_node.name}"
            
            # 5. Collega Color texture al primo input del Math node
            color_connected = False
            ao_connected = False
            
            for i, input_socket in enumerate(math_node.inputs):
                input_name = input_socket.name.lower() if hasattr(input_socket, 'name') else ''
                
                # Primo input: Color texture
                if not color_connected and (i == 0 or 'value1' in input_name or 'input1' in input_name or 'a' in input_name or 'color1' in input_name):
                    node_tree.links.new(existing_color_link.from_socket, input_socket)
                    color_connected = True
                    if color_source_node:
                        color_source_node.label = (color_source_node.label or color_source_node.name) + " →Math"
                
                # Secondo input: AO texture
                elif not ao_connected and (i == 1 or 'value2' in input_name or 'input2' in input_name or 'b' in input_name or 'color2' in input_name):
                    if 'Color' in texture_node.outputs:
                        node_tree.links.new(texture_node.outputs['Color'], input_socket)
                        ao_connected = True
                        texture_node.label += " →Math"
            
            # Fallback: usa i primi due input se non trovati per nome
            if not color_connected and len(math_node.inputs) > 0:
                node_tree.links.new(existing_color_link.from_socket, math_node.inputs[0])
                color_connected = True
                if color_source_node:
                    color_source_node.label = (color_source_node.label or color_source_node.name) + " →Math"
            
            if not ao_connected and len(math_node.inputs) > 1:
                if 'Color' in texture_node.outputs:
                    node_tree.links.new(texture_node.outputs['Color'], math_node.inputs[1])
                    ao_connected = True
                    texture_node.label += " →Math"
            
            # 6. Rimuovi il collegamento esistente Color → Disney
            node_tree.links.remove(existing_color_link)
            
            # 7. Collega l'output del Math node al Base Color del Disney
            if color_connected and ao_connected:
                output_socket = None
                for out_socket in math_node.outputs:
                    out_name = out_socket.name.lower() if hasattr(out_socket, 'name') else ''
                    if 'value' in out_name or 'color' in out_name or 'result' in out_name:
                        output_socket = out_socket
                        break
                
                if not output_socket and len(math_node.outputs) > 0:
                    output_socket = math_node.outputs[0]
                
                if output_socket:
                    node_tree.links.new(output_socket, color_input)
                    math_node.label += " →Color"
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error connecting AO: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def connect_opacity(self, node_tree, texture_node, disney_node):
        """Connect opacity/mask texture to Disney Opacity input"""
        if 'Opacity' in disney_node.inputs and hasattr(texture_node, 'outputs'):
            if 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], disney_node.inputs['Opacity'])
                texture_node.label = f"OPACITY: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
                
                return True
        return False
    
    def connect_height(self, node_tree, texture_node, disney_node, material_output, height):
        if not material_output:
            self.report({'WARNING'}, "No Material Output found")
            return False
        
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
                return False
            
            displacement_node.location = (disney_node.location.x - 300, texture_node.location.y)
            displacement_node.label = "Height Displacement"
            
            if hasattr(displacement_node, 'height'):
                displacement_node.height = height
            elif hasattr(displacement_node, 'value'):
                displacement_node.value = height
            
            if hasattr(displacement_node, 'scale'):
                displacement_node.scale = 0.02
            
            smooth_normals_props = ['normal_smooth', 'smooth_normals', 'smooth_normal', 'normal_smoothing']
            for prop_name in smooth_normals_props:
                if hasattr(displacement_node, prop_name):
                    try:
                        setattr(displacement_node, prop_name, True)
                        texture_node.label += " [Smooth]"
                        break
                    except:
                        continue
            
            if hasattr(texture_node, 'outputs') and 'Color' in texture_node.outputs:
                height_input = None
                for inp in displacement_node.inputs:
                    if 'height' in inp.name.lower():
                        height_input = inp
                        break
                if not height_input and len(displacement_node.inputs) > 0:
                    height_input = displacement_node.inputs[0]
                
                node_tree.links.new(texture_node.outputs['Color'], height_input)
                texture_node.label = f"HEIGHT: {texture_node.label or texture_node.name}"
                
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
            
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
            
            if hasattr(displacement_node, 'outputs') and len(displacement_node.outputs) > 0:
                # Collega Height Displacement → Material Output
                shape_input = None
                for inp in material_output.inputs:
                    if 'shape' in inp.name.lower() or 'displacement' in inp.name.lower():
                        shape_input = inp
                        break
                
                if shape_input:
                    shape_output = None
                    for out in displacement_node.outputs:
                        if 'shape' in out.name.lower():
                            shape_output = out
                            break
                    if not shape_output and len(displacement_node.outputs) > 0:
                        shape_output = displacement_node.outputs[0]
                    
                    node_tree.links.new(shape_output, shape_input)
                    return True
            
        except Exception as e:
            print(f"Error connecting height: {e}")
        
        return False
    
    def connect_emission(self, node_tree, texture_node, disney_node):
        """Collega texture Emission attraverso un nodo Emission intermedio"""
        try:
            # Crea il nodo Emission (LuxCoreNodeMatEmission)
            try:
                emission_node = node_tree.nodes.new(type='LuxCoreNodeMatEmission')
            except Exception as e:
                self.report({'ERROR'}, f"Cannot create Emission node: {e}")
                return False
            
            # Posiziona il nodo Emission tra la texture e il Disney node
            emission_node.location = (disney_node.location.x - 300, texture_node.location.y)
            emission_node.label = "Emission"
            
            # Collega la texture al pin Color del nodo Emission
            if hasattr(texture_node, 'outputs') and 'Color' in texture_node.outputs:
                if hasattr(emission_node, 'inputs'):
                    # Cerca il pin Color nel nodo Emission
                    color_input = None
                    for input_socket in emission_node.inputs:
                        if 'color' in input_socket.name.lower():
                            color_input = input_socket
                            break
                    
                    if color_input:
                        node_tree.links.new(texture_node.outputs['Color'], color_input)
                        texture_node.label = f"EMISSION: {texture_node.label or texture_node.name}"
                        
                        # Imposta gamma sRGB per emission (è un colore)
                        if hasattr(texture_node, 'color_space'):
                            texture_node.color_space = 'sRGB'
                    else:
                        self.report({'ERROR'}, "Color input not found in Emission node")
                        return False
            
            # Collega il nodo Emission al pin Emission del Disney node
            if hasattr(emission_node, 'outputs') and len(emission_node.outputs) > 0:
                emission_output = emission_node.outputs[0]
                
                # Cerca il pin Emission nel Disney node
                if 'Emission' in disney_node.inputs:
                    node_tree.links.new(emission_output, disney_node.inputs['Emission'])
                    return True
                else:
                    # Cerca con nomi alternativi
                    for input_socket in disney_node.inputs:
                        if 'emission' in input_socket.name.lower() or 'emit' in input_socket.name.lower():
                            node_tree.links.new(emission_output, input_socket)
                            return True
                    
                    self.report({'ERROR'}, "Emission input not found in Disney node")
                    return False
            
        except Exception as e:
            print(f"Error connecting Emission: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def connect_orm(self, node_tree, texture_node, disney_node):
        """Collega texture ORM: R=Occlusione, G=Roughness, B=Metallic - Con AO moltiplicato alla Color"""
        try:
            # Crea nodo Split RGB
            split_node = node_tree.nodes.new(type="LuxCoreNodeTexSplitFloat3")
            split_node.location = (disney_node.location.x - 400, texture_node.location.y)
            split_node.label = "Split ORM"
            
            # Collega la texture ORM al nodo split
            if hasattr(texture_node, 'outputs') and 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], split_node.inputs[0])
                texture_node.label = f"ORM: {texture_node.label or texture_node.name}"
                
                # Imposta come non-colore
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
            
            # Collega Roughness (canale G)
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 1:
                roughness_output = split_node.outputs[1]
                if 'Roughness' in disney_node.inputs:
                    node_tree.links.new(roughness_output, disney_node.inputs['Roughness'])
            
            # Collega Metallic (canale B)
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                metallic_output = split_node.outputs[2]
                if 'Metallic' in disney_node.inputs:
                    node_tree.links.new(metallic_output, disney_node.inputs['Metallic'])
            
            # Gestisce Occlusion (canale R) moltiplicato con Color texture
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 0:
                ao_output = split_node.outputs[0]  # Channel R
                
                # Cerca una texture Color esistente nel node tree
                color_node = None
                for node in node_tree.nodes:
                    if hasattr(node, 'label') and 'COLOR' in node.label.upper():
                        color_node = node
                        break
                
                # Se esiste una Color texture, moltiplica AO con Color
                if color_node:
                    self.multiply_ao_with_color(node_tree, disney_node, color_node, ao_output, texture_node)
            
            return True
            
        except Exception as e:
            print(f"Error connecting ORM: {e}")
        
        return False
    
    def connect_ors(self, node_tree, texture_node, disney_node):
        """Collega texture ORS: R=Occlusione, G=Roughness, B=Specular - Con AO moltiplicato alla Color"""
        try:
            # Crea nodo Split RGB
            split_node = node_tree.nodes.new(type="LuxCoreNodeTexSplitFloat3")
            split_node.location = (disney_node.location.x - 400, texture_node.location.y)
            split_node.label = "Split ORS"
            
            # Collega la texture ORS al nodo split
            if hasattr(texture_node, 'outputs') and 'Color' in texture_node.outputs:
                node_tree.links.new(texture_node.outputs['Color'], split_node.inputs[0])
                texture_node.label = f"ORS: {texture_node.label or texture_node.name}"
                
                # Imposta come non-colore
                if hasattr(texture_node, 'color_space'):
                    texture_node.color_space = 'Non-Color'
                elif hasattr(texture_node, 'gamma'):
                    texture_node.gamma = 1.0
            
            # Collega Roughness (canale G)
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 1:
                roughness_output = split_node.outputs[1]
                if 'Roughness' in disney_node.inputs:
                    node_tree.links.new(roughness_output, disney_node.inputs['Roughness'])
            
            # Collega Specular (canale B)
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 2:
                specular_output = split_node.outputs[2]
                if 'Specular' in disney_node.inputs:
                    node_tree.links.new(specular_output, disney_node.inputs['Specular'])
            
            # Gestisce Occlusion (canale R) moltiplicato con Color texture
            if hasattr(split_node, 'outputs') and len(split_node.outputs) > 0:
                ao_output = split_node.outputs[0]  # Channel R
                
                # Cerca una texture Color esistente nel node tree
                color_node = None
                for node in node_tree.nodes:
                    if hasattr(node, 'label') and 'COLOR' in node.label.upper():
                        color_node = node
                        break
                
                # Se esiste una Color texture, moltiplica AO con Color
                if color_node:
                    self.multiply_ao_with_color(node_tree, disney_node, color_node, ao_output, texture_node)
            
            return True
            
        except Exception as e:
            print(f"Error connecting ORS: {e}")
        
        return False
    
    
    def multiply_ao_with_color(self, node_tree, material_node, color_node, ao_channel, ao_source_node=None):
        """Multiply AO channel with Color and connect to Base Color"""
        try:
            # Create a Math node for multiplication (or ColorMix in scale mode)
            multiply_node_types = [
                'LuxCoreNodeTexMath',
                'LuxCoreNodeMath',
                'LuxCoreNodeTexMix',
                'LuxCoreNodeTexMixColor',
                'luxcore_tex_math',
                'luxcore_tex_mix',
            ]
            
            multiply_node = None
            for node_type in multiply_node_types:
                try:
                    multiply_node = node_tree.nodes.new(type=node_type)
                    break
                except:
                    continue
            
            if not multiply_node:
                print("ERROR: Cannot create multiply node")
                return False
            
            multiply_node.location = (material_node.location.x - 300, 
                                     color_node.location.y if color_node else material_node.location.y)
            multiply_node.label = "AO Multiply"
            
            # Set operation to Multiply if available
            if hasattr(multiply_node, 'operation'):
                multiply_node.operation = 'MULTIPLY'
            elif hasattr(multiply_node, 'mode'):
                multiply_node.mode = 'scale'
            
            # Get color output from color node
            color_output = None
            if color_node and hasattr(color_node, 'outputs') and len(color_node.outputs) > 0:
                for output in color_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output and len(color_node.outputs) > 0:
                    color_output = color_node.outputs[0]
            
            # If no color texture, create a white constant
            if not color_output:
                white_node = node_tree.nodes.new(type='LuxCoreNodeTexConstantFloat3')
                white_node.location = (multiply_node.location.x - 200, multiply_node.location.y)
                white_node.value = (1.0, 1.0, 1.0)
                white_node.label = "White"
                color_output = white_node.outputs[0] if len(white_node.outputs) > 0 else None
            
            # Connect color to first input of multiply node
            if color_output:
                if len(multiply_node.inputs) > 0:
                    node_tree.links.new(color_output, multiply_node.inputs[0])
                    print(f"DEBUG: Color connected to multiply node")
            
            # Connect AO channel to second input of multiply node
            if ao_channel and len(multiply_node.inputs) > 1:
                node_tree.links.new(ao_channel, multiply_node.inputs[1])
                print(f"DEBUG: AO channel connected to multiply node")
                if ao_source_node:
                    ao_source_node.label = f"AO: {ao_source_node.label or ao_source_node.name}"
            
            # Connect multiply output to Base Color
            if len(multiply_node.outputs) > 0 and 'Base Color' in material_node.inputs:
                multiply_output = None
                for output in multiply_node.outputs:
                    if output.name.lower() in ['color', 'value', 'result']:
                        multiply_output = output
                        break
                if not multiply_output and len(multiply_node.outputs) > 0:
                    multiply_output = multiply_node.outputs[0]
                
                if multiply_output:
                    # Remove existing connection to Base Color if any
                    base_color_input = material_node.inputs['Base Color']
                    for link in node_tree.links:
                        if link.to_socket == base_color_input:
                            node_tree.links.remove(link)
                            break
                    
                    node_tree.links.new(multiply_output, base_color_input)
                    print(f"DEBUG: Multiply output connected to Base Color")
                    return True
            
        except Exception as e:
            print(f"ERROR in multiply_ao_with_color: {str(e)}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def activate_normal_map(self, texture_node, normal_strength):
        try:
            normalmap_props = [
                'normalmap', 'normal_map', 'use_normalmap', 'use_normal_map',
                'is_normalmap', 'is_normal_map', 'normal', 'as_normal',
                'use_as_normalmap'
            ]
            
            for prop_name in normalmap_props:
                if hasattr(texture_node, prop_name):
                    try:
                        setattr(texture_node, prop_name, True)
                        break
                    except:
                        continue
            
            bump_props = [
                'bump_height', 'height', 'strength', 'normal_strength',
                'normal_scale', 'scale', 'value', 'intensity'
            ]
            for prop_name in bump_props:
                if hasattr(texture_node, prop_name):
                    try:
                        setattr(texture_node, prop_name, normal_strength)
                        break
                    except:
                        continue
                        
        except Exception as e:
            print(f"Error activating normal map: {e}")

class NODE_MT_luxcore_connect_selected_menu(Menu):
    bl_label = "Connect Texture"
    bl_idname = "NODE_MT_luxcore_connect_selected_menu"
    
    def draw(self, context):
        layout = self.layout
        
        types = [
            ('COLOR', "Color", 'MATERIAL'),
            ('ROUGHNESS', "Roughness", 'NODE_TEXTURE'),
            ('NORMAL', "Normal", 'NORMALS_FACE'),
            ('BUMP', "Bump", 'MOD_SMOOTH'),
            ('SPECULAR', "Specular", 'SHADING_SOLID'),
            ('METALLIC', "Metallic", 'SHADING_WIRE'),
            ('OCCLUSION', "Occlusion", 'LIGHT_HEMI'),
            ('HEIGHT', "Height", 'MOD_DISPLACE'),
            ('OPACITY', "Opacity/Mask", 'IMAGE_ALPHA'),
            ('EMISSION', "Emission", 'LIGHT'),
            ('ORM', "ORM", 'NODE_TEXTURE'),
            ('ORS', "ORS", 'NODE_TEXTURE'),
        ]
        
        for type_id, label, icon in types:
            op = layout.operator(
                LUXCORE_OT_connect_selected_texture.bl_idname,
                text=label,
                icon=icon
            )
            op.texture_type = type_id

def draw_luxcore_connect_selected_menu(self, context):
    if not context.space_data or not context.space_data.node_tree:
        return
    
    node_tree = context.space_data.node_tree
    active_node = node_tree.nodes.active
    
    if not active_node:
        return
    
    texture_node_types = [
        'LuxCoreNodeTexImagemap',
        'LuxCoreNodeTexImage',
        'ShaderNodeTexImage'
    ]
    
    if active_node.bl_idname in texture_node_types:
        layout = self.layout
        layout.separator()
        layout.menu("NODE_MT_luxcore_connect_selected_menu")

def register():
    bpy.utils.register_class(LUXCORE_OT_connect_selected_texture)
    bpy.utils.register_class(NODE_MT_luxcore_connect_selected_menu)
    
    bpy.types.NODE_MT_context_menu.append(draw_luxcore_connect_selected_menu)
    bpy.types.NODE_MT_node.append(draw_luxcore_connect_selected_menu)

def unregister():
    bpy.utils.unregister_class(LUXCORE_OT_connect_selected_texture)
    bpy.utils.unregister_class(NODE_MT_luxcore_connect_selected_menu)
    
    bpy.types.NODE_MT_context_menu.remove(draw_luxcore_connect_selected_menu)
    bpy.types.NODE_MT_node.remove(draw_luxcore_connect_selected_menu)

if __name__ == "__main__":
    register()
