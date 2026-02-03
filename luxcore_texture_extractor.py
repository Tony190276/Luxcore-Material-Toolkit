bl_info = {
    "name": "LuxCore Texture Extractor",
    "author": "Tony",
    "version": (3, 4, 0),  # Separate bump from normal, added mask keyword to opacity
    "blender": (4, 2, 0),
    "location": "Properties > Material > LuxCore Texture Extractor",
    "description": "Extract textures from active material, import them to LuxCore and connect automatically",
    "category": "Material",
    "support": "COMMUNITY",
}

import bpy
import re
import os
from bpy.types import Panel, Operator, Menu
from bpy.props import StringProperty, BoolProperty, CollectionProperty, IntProperty, EnumProperty

class LUXCORE_EXTRACT_OT_extract_textures(Operator):
    """Extract all textures from active material selected in Material Properties window"""
    bl_idname = "luxcore_extract.extract_textures"
    bl_label = "Extract Textures to LuxCore"
    bl_options = {'REGISTER', 'UNDO'}
    
    only_used_textures: BoolProperty(
        name="Only Used Textures",
        description="Extract only textures actually connected to material",
        default=True
    )
    
    create_luxcore_material: BoolProperty(
        name="Create LuxCore Material",
        description="Automatically create a LuxCore Disney material",
        default=True
    )
    
    auto_connect: BoolProperty(
        name="Auto Connect",
        description="Automatically connect textures to Disney material",
        default=True
    )
    
    create_uv_node: BoolProperty(
        name="Create UV Node",
        description="Create a shared 2D Mapping node for all textures",
        default=True,
    )
    
    transfer_principled_values: BoolProperty(
        name="Transfer Principled Values",
        description="Transfer numeric values from Principled BSDF to Disney node (Base Color, Metallic, Roughness, etc.)",
        default=True,
    )
    
    @classmethod
    def poll(cls, context):
        return hasattr(context, 'material') and context.material is not None
    
    def execute(self, context):
        original_material = context.material
        
        if not original_material:
            self.report({'ERROR'}, "No material selected in Material Properties window")
            return {'CANCELLED'}
        
        print(f"=== LUXCORE EXTRACTOR: Extracting textures from material '{original_material.name}' ===")
        
        target_material = None
        luxcore_material_name = f"{original_material.name}_LuxCore"
        
        if luxcore_material_name in bpy.data.materials:
            target_material = bpy.data.materials[luxcore_material_name]
            print(f"Found existing LuxCore material: {target_material.name}")
        elif self.create_luxcore_material:
            target_material = self.create_luxcore_material_with_preset(context, luxcore_material_name)
            
            if target_material:
                print(f"Created new LuxCore Disney material: {target_material.name}")
            else:
                self.report({'ERROR'}, "Cannot create LuxCore Disney material")
                return {'CANCELLED'}
        else:
            target_material = original_material
            print(f"Using original material: {target_material.name}")
        
        # Extract Principled BSDF values before processing textures
        principled_values = None
        if self.transfer_principled_values:
            principled_values = self.extract_principled_values(original_material)
            if principled_values:
                print(f"Extracted {len(principled_values)} values from Principled BSDF")
        
        found_textures = self.extract_textures_from_active_material(original_material)
        
        if not found_textures and not principled_values:
            self.report({'WARNING'}, f"No textures or values found in material '{original_material.name}'")
            return {'CANCELLED'}
        
        created_texture_nodes = []
        if found_textures:
            created_texture_nodes = self.create_luxcore_texture_nodes(context, target_material, found_textures)
        
        if created_texture_nodes or principled_values:
            if self.auto_connect and created_texture_nodes:
                success = self.auto_connect_textures(context, target_material, created_texture_nodes)
                if success:
                    self.report({'INFO'}, f"Extracted and connected {len(created_texture_nodes)} textures to '{target_material.name}'")
                else:
                    self.report({'WARNING'}, f"Textures created but connection failed")
            elif created_texture_nodes:
                self.report({'INFO'}, f"Extracted {len(created_texture_nodes)} textures to '{target_material.name}'")
            
            # Apply Principled values to Disney node
            if principled_values and self.transfer_principled_values:
                values_applied = self.apply_principled_values_to_disney(target_material, principled_values)
                if values_applied > 0:
                    print(f"Applied {values_applied} Principled values to Disney node")
            
            self.open_luxcore_node_editor(context, target_material)
        else:
            self.report({'ERROR'}, "Cannot create texture nodes")
        
        return {'FINISHED'}
    
    def create_luxcore_material_with_preset(self, context, name):
        try:
            active_object = context.active_object
            active_material_index = active_object.active_material_index if active_object else 0
            
            try:
                bpy.ops.luxcore.preset_material(preset='Disney')
            except:
                pass
            
            if active_object and active_object.active_material:
                new_mat = active_object.active_material
                new_mat.name = name
                return new_mat
            else:
                return self.create_luxcore_material_manual(name, 'Disney')
                
        except Exception as e:
            print(f"Error creating Disney material: {e}")
            return self.create_luxcore_material_manual(name, 'Disney')
    
    def create_luxcore_material_manual(self, name, preset_type='Disney'):
        try:
            mat = bpy.data.materials.new(name=name)
            
            if hasattr(mat, 'luxcore'):
                mat.luxcore.enabled = True
                
                # Note: make_nodetree_name and init_mat_node_tree functions might be in a utils module
                # We'll create a fallback if they're not available
                try:
                    from .utils import make_nodetree_name, init_mat_node_tree
                    tree_name = make_nodetree_name(mat.name)
                    node_tree = bpy.data.node_groups.new(name=tree_name, type="luxcore_material_nodes")
                    init_mat_node_tree(node_tree)
                    mat.luxcore.node_tree = node_tree
                except:
                    # Fallback if utils module is not available
                    mat.use_nodes = True
                
                print(f"Manually created LuxCore material: {mat.name}")
                return mat
            else:
                mat.use_nodes = True
                print(f"Created standard material (LuxCore not available): {mat.name}")
                return mat
                
        except Exception as e:
            print(f"Error manually creating material: {e}")
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            return mat
    
    def extract_principled_values(self, material):
        """Extract numeric values from Principled BSDF node (only for inputs without texture connections)"""
        values = {}
        
        if not material.use_nodes or not material.node_tree:
            print("Material doesn't use nodes")
            return values
        
        # Find the Principled BSDF node
        principled_node = None
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                principled_node = node
                break
        
        if not principled_node:
            print("No Principled BSDF node found")
            return values
        
        print(f"Found Principled BSDF node: {principled_node.name}")
        
        # Mapping of Principled BSDF inputs to Disney inputs
        # Format: 'Principled Input Name': ('Disney Input Name', invert, is_color)
        value_mapping = {
            'Base Color': ('Base Color', False, True),
            'Metallic': ('Metallic', False, False),
            'Roughness': ('Roughness', False, False),
            'Specular IOR Level': ('Specular', False, False),  # Blender 4.0+
            'Specular': ('Specular', False, False),  # Blender 3.x fallback
            'Sheen Weight': ('Sheen', False, False),  # Blender 4.0+
            'Sheen': ('Sheen', False, False),  # Blender 3.x fallback
            'Sheen Tint': ('Sheen Tint', False, False),
            'Coat Weight': ('Clearcoat', False, False),  # Blender 4.0+
            'Clearcoat': ('Clearcoat', False, False),  # Blender 3.x fallback
            'Coat Roughness': ('Clearcoat Gloss', True, False),  # Blender 4.0+ - INVERTED
            'Clearcoat Roughness': ('Clearcoat Gloss', True, False),  # Blender 3.x - INVERTED
            'Alpha': ('Opacity', False, False),
            'Emission Color': ('Emission Color', False, True),  # Special handling for emission
            'Emission Strength': ('Emission Strength', False, False),  # To check if emission is active
        }
        
        for principled_input, (disney_input, invert, is_color) in value_mapping.items():
            if principled_input in principled_node.inputs:
                input_socket = principled_node.inputs[principled_input]
                
                # Check if input has a texture connected
                if input_socket.is_linked:
                    print(f"  {principled_input}: has texture connected, skipping value")
                    continue
                
                # Get the default value
                try:
                    if is_color:
                        # Color values (RGBA)
                        default_value = input_socket.default_value
                        if hasattr(default_value, '__iter__'):
                            color_value = tuple(default_value[:3])  # Get RGB, ignore Alpha
                            values[disney_input] = {
                                'value': color_value,
                                'is_color': True,
                                'invert': invert
                            }
                            print(f"  {principled_input} -> {disney_input}: RGB{color_value}")
                    else:
                        # Scalar values
                        value = float(input_socket.default_value)
                        if invert:
                            value = 1.0 - value
                        values[disney_input] = {
                            'value': value,
                            'is_color': False,
                            'invert': invert
                        }
                        print(f"  {principled_input} -> {disney_input}: {value}" + (" (inverted)" if invert else ""))
                except Exception as e:
                    print(f"  Error extracting {principled_input}: {e}")
        
        return values
    
    def apply_principled_values_to_disney(self, material, principled_values):
        """Apply extracted Principled BSDF values to Disney node"""
        applied_count = 0
        
        # Get the LuxCore node tree
        luxcore_tree = None
        if hasattr(material, 'luxcore') and material.luxcore.node_tree:
            luxcore_tree = material.luxcore.node_tree
        elif material.node_tree:
            luxcore_tree = material.node_tree
        else:
            print("ERROR: No node tree found for applying values")
            return 0
        
        # Find the Disney node
        disney_node = None
        for node in luxcore_tree.nodes:
            if node.bl_idname in ['LuxCoreNodeMatDisney', 'LuxCoreNodeMatDisney2', 'luxcore_material_disney']:
                disney_node = node
                break
        
        if not disney_node:
            print("ERROR: No Disney node found")
            return 0
        
        print(f"Applying values to Disney node: {disney_node.name}")
        
        # Debug: print all available inputs in Disney node
        print(f"  DEBUG: Available Disney inputs: {[inp.name for inp in disney_node.inputs]}")
        
        # Check for emission - only create if color is NOT black
        emission_color = principled_values.get('Emission Color')
        emission_strength = principled_values.get('Emission Strength')
        
        has_valid_emission = False
        if emission_color:
            color = emission_color['value']
            # Check if emission color is NOT black (all components > threshold)
            color_threshold = 0.001
            if any(c > color_threshold for c in color):
                # Also check emission strength if available
                if emission_strength:
                    if emission_strength['value'] > 0:
                        has_valid_emission = True
                else:
                    # No strength info, but color is not black
                    has_valid_emission = True
        
        if has_valid_emission and emission_color:
            print(f"  Emission detected (color: {emission_color['value']}), creating Emission node...")
            if self.create_emission_from_values(luxcore_tree, disney_node, emission_color['value']):
                applied_count += 1
        else:
            print("  No valid emission (color is black or strength is 0), skipping Emission node")
        
        # Apply other values to Disney node inputs
        for disney_input, value_info in principled_values.items():
            # Skip emission values (handled separately)
            if disney_input in ['Emission Color', 'Emission Strength']:
                continue
            
            # Try to find the socket with exact name or alternatives
            target_socket = None
            target_name = disney_input
            
            # First try exact match
            if disney_input in disney_node.inputs:
                target_socket = disney_node.inputs[disney_input]
                target_name = disney_input
            else:
                # Try alternative socket names
                alt_names = self.get_alternative_socket_names(disney_input)
                for alt_name in alt_names:
                    if alt_name in disney_node.inputs:
                        target_socket = disney_node.inputs[alt_name]
                        target_name = alt_name
                        break
                
                # If still not found, try case-insensitive search
                if not target_socket:
                    for inp in disney_node.inputs:
                        if inp.name.lower() == disney_input.lower():
                            target_socket = inp
                            target_name = inp.name
                            break
                        # Also check for partial match
                        for alt_name in alt_names + [disney_input]:
                            if alt_name.lower() in inp.name.lower() or inp.name.lower() in alt_name.lower():
                                target_socket = inp
                                target_name = inp.name
                                break
                        if target_socket:
                            break
            
            if target_socket:
                # Skip if already has a texture connected
                if target_socket.is_linked:
                    print(f"  {disney_input}: already has connection, skipping")
                    continue
                
                try:
                    if value_info['is_color']:
                        # Set color value - handle different socket types
                        color_val = value_info['value']
                        if hasattr(target_socket, 'default_value'):
                            # Check socket type
                            socket_type = type(target_socket.default_value)
                            if hasattr(target_socket.default_value, '__len__'):
                                if len(target_socket.default_value) == 4:
                                    target_socket.default_value = (color_val[0], color_val[1], color_val[2], 1.0)
                                elif len(target_socket.default_value) == 3:
                                    target_socket.default_value = color_val
                                else:
                                    target_socket.default_value = color_val[0]  # Use first component
                            else:
                                target_socket.default_value = color_val[0]
                        print(f"  Applied {disney_input} -> {target_name}: RGB{color_val}")
                        applied_count += 1
                    else:
                        # Set scalar value
                        target_socket.default_value = value_info['value']
                        print(f"  Applied {disney_input} -> {target_name}: {value_info['value']}")
                        applied_count += 1
                except Exception as e:
                    print(f"  Error applying {disney_input} -> {target_name}: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"  Socket not found for {disney_input}, tried alternatives: {self.get_alternative_socket_names(disney_input)}")
        
        return applied_count
    
    def get_alternative_socket_names(self, socket_name):
        """Get alternative socket names for compatibility"""
        alternatives = {
            'Base Color': ['BaseColor', 'Diffuse Color', 'Color', 'Diffuse'],
            'Metallic': ['Metal', 'Metallicness'],
            'Roughness': ['Rough', 'Glossiness'],
            'Specular': ['Spec', 'Specular Level', 'Reflection'],
            'Sheen': ['Sheen Weight', 'SheenAmount'],
            'Sheen Tint': ['SheenTint', 'Sheen Color'],
            'Clearcoat': ['Coat', 'Clear Coat', 'ClearCoat', 'Coat Weight'],
            'Clearcoat Gloss': ['Coat Gloss', 'ClearCoatGloss', 'Clearcoat Roughness'],
            'Opacity': ['Alpha', 'Transparency'],
        }
        return alternatives.get(socket_name, [])
    
    def create_emission_from_values(self, node_tree, disney_node, emission_color):
        """Create an Emission node with the specified color and connect it to Disney"""
        try:
            # Create Emission node
            emission_node = node_tree.nodes.new(type='LuxCoreNodeMatEmission')
            emission_node.location = (disney_node.location.x - 300, disney_node.location.y - 200)
            emission_node.label = "Emission (from Principled)"
            
            # Set emission color on "Color" input (capital C as per LuxCore source)
            if "Color" in emission_node.inputs:
                color_input = emission_node.inputs["Color"]
                # Set RGB color (LuxCore Color socket expects RGB tuple or RGBA)
                try:
                    # Try setting as RGB first
                    color_input.default_value = emission_color
                    print(f"    Set emission color (RGB): {emission_color}")
                except:
                    try:
                        # Try with alpha
                        color_input.default_value = (*emission_color, 1.0)
                        print(f"    Set emission color (RGBA): {emission_color}")
                    except Exception as e:
                        print(f"    Could not set color: {e}")
            else:
                print(f"    WARNING: 'Color' input not found in Emission node")
                print(f"    Available inputs: {[inp.name for inp in emission_node.inputs]}")
            
            # Connect Emission node output to Disney's "Emission" input
            # The output socket should be index 0 or named "Emission"
            emission_output = emission_node.outputs[0]
            
            # Find "Emission" input in Disney node
            if "Emission" in disney_node.inputs:
                emission_input = disney_node.inputs["Emission"]
                node_tree.links.new(emission_output, emission_input)
                print(f"    Connected Emission node to Disney 'Emission' input")
                return True
            else:
                # Try case-insensitive search
                for inp in disney_node.inputs:
                    if 'emission' in inp.name.lower():
                        node_tree.links.new(emission_output, inp)
                        print(f"    Connected Emission node to Disney '{inp.name}' input")
                        return True
                
                print(f"    WARNING: Could not find Emission input in Disney node")
                print(f"    Available inputs: {[inp.name for inp in disney_node.inputs]}")
            
            return False
            
        except Exception as e:
            print(f"    Error creating Emission node: {e}")
            import traceback
            traceback.print_exc()
            return False

    def extract_textures_from_active_material(self, material):
        textures = []
        
        if not material.use_nodes:
            print(f"Material '{material.name}' doesn't use nodes")
            return textures
        
        processed_images = set()
        
        def explore_node_tree(node_tree, tree_name="root"):
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if node.image.name not in processed_images:
                        texture_info = {
                            'name': node.image.name,
                            'image': node.image,
                            'node_name': node.name,
                            'material_name': material.name,
                            'is_connected': any(len(output.links) > 0 for output in node.outputs),
                            'filepath': node.image.filepath if node.image.filepath else node.image.name,
                            'node_tree': tree_name
                        }
                        
                        if self.is_node_connected_to_material(node, node_tree):
                            textures.append(texture_info)
                            processed_images.add(node.image.name)
                            print(f"Found texture: {node.image.name} in node {node.name}")
                        else:
                            print(f"Ignored unconnected texture: {node.image.name}")
                
                elif node.type == 'GROUP' and node.node_tree:
                    print(f"Exploring group: {node.node_tree.name}")
                    explore_node_tree(node.node_tree, f"{tree_name} > {node.node_tree.name}")
                
                elif node.type == 'TEX_ENVIRONMENT' and node.image:
                    if node.image.name not in processed_images:
                        texture_info = {
                            'name': node.image.name,
                            'image': node.image,
                            'node_name': node.name,
                            'material_name': material.name,
                            'is_connected': any(len(output.links) > 0 for output in node.outputs),
                            'type': 'ENVIRONMENT',
                            'filepath': node.image.filepath if node.image.filepath else node.image.name,
                            'node_tree': tree_name
                        }
                        
                        if self.is_node_connected_to_material(node, node_tree):
                            textures.append(texture_info)
                            processed_images.add(node.image.name)
                            print(f"Found environment texture: {node.image.name}")
                        else:
                            print(f"Ignored unconnected environment texture: {node.image.name}")
        
        print(f"Exploring node tree of material '{material.name}'")
        explore_node_tree(material.node_tree)
        
        if self.only_used_textures:
            filtered_textures = [t for t in textures if t['is_connected']]
            print(f"Filtered textures (only connected): {len(filtered_textures)} out of {len(textures)}")
            return filtered_textures
        
        print(f"Total textures found: {len(textures)}")
        return textures
    
    def is_node_connected_to_material(self, node, node_tree):
        for output in node.outputs:
            if output.links:
                for link in output.links:
                    if self.traverse_to_material_output(link.to_node, node_tree):
                        return True
        
        if node.type == 'BSDF_PRINCIPLED':
            for output in node.outputs:
                for link in output.links:
                    if link.to_node.type == 'OUTPUT_MATERIAL':
                        return True
        
        return False
    
    def traverse_to_material_output(self, node, node_tree, visited=None):
        if visited is None:
            visited = set()
        
        if node in visited:
            return False
        visited.add(node)
        
        if node.type == 'OUTPUT_MATERIAL':
            return True
        
        if node.type == 'GROUP' and node.node_tree:
            for n in node.node_tree.nodes:
                if n.type == 'OUTPUT_MATERIAL':
                    return True
        
        for output in node.outputs:
            for link in output.links:
                if self.traverse_to_material_output(link.to_node, node_tree, visited):
                    return True
        
        return False
    
    def create_luxcore_texture_nodes(self, context, material, found_textures):
        luxcore_tree = None
        
        if hasattr(material, 'luxcore') and material.luxcore.node_tree:
            luxcore_tree = material.luxcore.node_tree
            print(f"Using existing LuxCore tree: {luxcore_tree.name}")
        elif material.node_tree:
            luxcore_tree = material.node_tree
            print(f"Using standard node tree: {luxcore_tree.name}")
        else:
            material.use_nodes = True
            luxcore_tree = material.node_tree
            print(f"Created new node tree for: {material.name}")
        
        for node in luxcore_tree.nodes:
            node.select = False
        
        start_x = -400
        start_y = 300
        
        output_node = None
        material_node = None
        
        for node in luxcore_tree.nodes:
            if 'output' in node.name.lower() or node.type == 'OUTPUT_MATERIAL' or node.bl_idname == 'LuxCoreNodeMatOutput':
                output_node = node
            elif 'disney' in node.name.lower() or 'glossy' in node.name.lower() or 'matte' in node.name.lower():
                material_node = node
            elif node.bl_idname in ['LuxCoreNodeMatDisney', 'LuxCoreNodeMatGlossy2', 'LuxCoreNodeMatMatte', 
                                  'LuxCoreNodeMatGlass', 'LuxCoreNodeMatMetal', 'LuxCoreNodeMatMirror']:
                material_node = node
        
        if output_node:
            start_x = output_node.location.x - 400
            start_y = output_node.location.y
            print(f"Using existing output node for positioning: {output_node.name}")
        elif material_node:
            start_x = material_node.location.x - 400
            start_y = material_node.location.y
            print(f"Using material node for positioning: {material_node.name}")
        
        created_nodes = []
        y_offset = 0
        
        for i, texture_info in enumerate(found_textures):
            try:
                tex_node = None
                
                if luxcore_tree.bl_idname == 'luxcore_material_nodes':
                    try:
                        tex_node = luxcore_tree.nodes.new('LuxCoreNodeTexImagemap')
                    except:
                        tex_node = luxcore_tree.nodes.new('LuxCoreNodeTexImage')
                else:
                    tex_node = luxcore_tree.nodes.new('ShaderNodeTexImage')
                
                tex_node.name = f"LuxCore_{texture_info['name'].replace('.', '_')}"
                tex_node.label = f"{texture_info['name']}"
                
                if texture_info.get('type') == 'ENVIRONMENT':
                    tex_node.label += " [ENV]"
                
                self.set_node_image(tex_node, texture_info['image'], texture_info.get('filepath', ''))
                
                tex_node.location = (start_x, start_y - y_offset)
                y_offset += 150
                
                created_nodes.append(tex_node)
                print(f"Created texture node for: {texture_info['name']}")
                
            except Exception as e:
                print(f"Error creating texture node for {texture_info['name']}: {e}")
        
        for node in created_nodes:
            node.select = True
        
        self.refresh_ui(context)
        
        return created_nodes
    
    def set_node_image(self, texture_node, blender_image, filepath):
        if hasattr(texture_node, 'image'):
            try:
                texture_node.image = blender_image
                print(f"Set image: {blender_image.name}")
                return True
            except Exception as e:
                print(f"Error setting 'image': {e}")
        
        if hasattr(texture_node, 'file'):
            try:
                if blender_image.filepath:
                    texture_node.file = blender_image.filepath
                else:
                    texture_node.file = blender_image.name
                print(f"Set file: {texture_node.file}")
                return True
            except Exception as e:
                print(f"Error setting 'file': {e}")
        
        if hasattr(texture_node, 'filename'):
            try:
                if blender_image.filepath:
                    texture_node.filename = blender_image.filepath
                else:
                    texture_node.filename = blender_image.name
                print(f"Set filename: {texture_node.filename}")
                return True
            except Exception as e:
                print(f"Error setting 'filename': {e}")
        
        for attr in dir(texture_node):
            if 'image' in attr.lower() or 'texture' in attr.lower():
                try:
                    setattr(texture_node, attr, blender_image)
                    print(f"Set attribute {attr}: {blender_image.name}")
                    return True
                except:
                    continue
        
        print(f"Could not set image in node: {blender_image.name}")
        return False
    
    def setup_normal_map_properties(self, tex_node):
        try:
            normal_strength = 1.0
            
            normal_map_props = [
                'is_normal_map', 'normal_map', 'use_normal_map', 
                'is_normal', 'normal', 'normalmap'
            ]
            
            for prop in normal_map_props:
                if hasattr(tex_node, prop):
                    try:
                        setattr(tex_node, prop, True)
                        print(f"Set {prop} to True for {tex_node.name}")
                        break
                    except:
                        continue
            
            scale_props = ['normal_scale', 'scale', 'strength', 'value', 'intensity']
            for prop in scale_props:
                if hasattr(tex_node, prop):
                    try:
                        setattr(tex_node, prop, normal_strength)
                        print(f"Set {prop} to {normal_strength} for {tex_node.name}")
                        break
                    except:
                        continue
                        
        except Exception as e:
            print(f"Error setting normal map properties: {e}")
    
    def auto_connect_textures(self, context, material, texture_nodes):
        try:
            luxcore_tree = None
            if hasattr(material, 'luxcore') and material.luxcore.node_tree:
                luxcore_tree = material.luxcore.node_tree
            elif material.node_tree:
                luxcore_tree = material.node_tree
            else:
                print("ERROR: No node tree found")
                return False
            
            material_node = None
            for node in luxcore_tree.nodes:
                if node.bl_idname in ['LuxCoreNodeMatDisney', 'LuxCoreNodeMatGlossy2', 'LuxCoreNodeMatMatte', 
                                    'LuxCoreNodeMatGlass', 'LuxCoreNodeMatMetal', 'LuxCoreNodeMatMirror',
                                    'LuxCoreNodeMatMix', 'LuxCoreNodeMatNull']:
                    material_node = node
                    break
            
            if not material_node:
                print("ERROR: No LuxCore material node found")
                return False
            
            mapping_node = None
            if self.create_uv_node:
                mapping_node = self.create_2d_mapping_node(luxcore_tree, material_node)
            
            material_output = self.find_or_create_material_output(luxcore_tree, material_node)
            
            connected_count = self.connect_textures_to_material(
                luxcore_tree, material_node, texture_nodes, mapping_node, material_output
            )
            
            if connected_count > 0:
                print(f"Connected {connected_count} textures to material {material_node.bl_idname}")
                self.organize_nodes(luxcore_tree, material_node, texture_nodes, mapping_node, material_output)
                return True
            else:
                print("No textures connected")
                return False
                
        except Exception as e:
            print(f"Error in auto connection: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def create_2d_mapping_node(self, node_tree, disney_node):
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
            print(f"Cannot create 2D Mapping node: {str(e)}")
        
        return None
    
    def find_or_create_material_output(self, node_tree, disney_node):
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
    
    def connect_textures_to_material(self, node_tree, material_node, texture_nodes, mapping_node, material_output):
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
            'emission': {
                'keywords': ['emission', 'emit', 'emissive', 'emiss', 'glow', 'light'],
                'socket': 'Emission',
                'is_emission': True,
                'priority': 10
            },
            'color': {
                'keywords': ['color', 'diff', 'diffuse', 'albedo', 'basecolor', 'col', 'base', 
                           'basecol', 'diffuse', 'dif', 'dff', 'clr', 'colour'],
                'socket': 'Base Color',
                'priority': 9
            },
            'normal': {
                'keywords': ['normal', 'norm', 'nrm', 'nor', 'normalmap', 'normal_map', 
                           'normalgl', 'normal_dx', 'nrml', 'normals',
                           'normal_gl', 'normalgl', 'norm_gl'],
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
                'keywords': ['metal', 'metallic', 'metallness', 'metalness', 'mtl', 'met', 'metalic'],
                'socket': 'Metallic',
                'priority': 6
            },
            'roughness': {
                'keywords': ['rough', 'roughness', 'rugosità', 'roughness', 'gloss', 'glossiness',
                           'rgh', 'roughness', 'rghns', 'rough', 'rug'],
                'socket': 'Roughness',
                'priority': 5
            },
            'specular': {
                'keywords': ['spec', 'specular', 'specularity', 'spc', 'specular', 'specularlevel'],
                'socket': 'Specular',
                'priority': 4
            },
            'height': {
                'keywords': ['height', 'disp', 'displacement', 'heightmap', 'height_map',
                           'hgt', 'displace', 'depth', 'depthmap'],
                'socket': 'Height',
                'is_height': True,
                'priority': 3
            },
            'opacity': {
                'keywords': ['opacity', 'alpha', 'transparency', 'transparent', 'opac',
                           'alph', 'trans', 'op', 'mask'],
                'socket': 'Opacity',
                'priority': 2
            },
            'ao': {
                'keywords': ['ao', 'ambientocclusion', 'occlusion', 'ambient', 'ambient_occlusion',
                           'occl', 'ambocc', 'ambientoccl', 'occlusion', 'ao_', '_ao', 'ao_map'],
                'is_ao': True,
                'priority': 1
            }
        }
        
        texture_info_list = []
        ao_texture_node = None
        color_texture_node = None
        orm_node = None
        ors_node = None
        orm_ao_channel = None
        ors_ao_channel = None
        
        # First pass: identify textures
        for tex_node in texture_nodes:
            node_name = tex_node.name.lower()
            image_name = ""
            
            if hasattr(tex_node, 'image') and tex_node.image:
                image_name = tex_node.image.name.lower()
            
            search_text = node_name + " " + image_name
            
            # Extract the suffix part (last segment before extension) for priority matching
            # This handles naming conventions like "Asset_Base_BaseColor.jpg" where the type is at the end
            import os
            basename_no_ext = os.path.splitext(image_name)[0] if image_name else os.path.splitext(node_name)[0]
            # Get the last segment after underscore, dash, or dot
            suffix_parts = re.split(r'[_\-\.]', basename_no_ext)
            suffix_text = suffix_parts[-1] if suffix_parts else ""
            
            best_match = None
            best_priority = -1
            best_is_suffix = False  # Track if match is from suffix (higher precedence)
            
            for tex_type, tex_info in texture_mapping.items():
                for keyword in tex_info['keywords']:
                    pattern = r'(^|[^a-zA-Z0-9])' + re.escape(keyword) + r'($|[^a-zA-Z0-9])'
                    
                    # First check if keyword matches in the suffix (end of filename)
                    suffix_pattern = r'^' + re.escape(keyword) + r'$'
                    is_suffix_match = bool(re.search(suffix_pattern, suffix_text, re.IGNORECASE))
                    
                    if re.search(pattern, search_text, re.IGNORECASE):
                        current_priority = tex_info.get('priority', 0)
                        
                        # Suffix matches get absolute priority over non-suffix matches
                        if is_suffix_match and not best_is_suffix:
                            best_priority = current_priority
                            best_match = (tex_type, tex_info)
                            best_is_suffix = True
                        elif is_suffix_match and best_is_suffix:
                            # Both are suffix matches, use priority
                            if current_priority > best_priority:
                                best_priority = current_priority
                                best_match = (tex_type, tex_info)
                        elif not is_suffix_match and not best_is_suffix:
                            # Neither is suffix match, use priority
                            if current_priority > best_priority:
                                best_priority = current_priority
                                best_match = (tex_type, tex_info)
                        # If current is not suffix but best is suffix, skip
                        break
            
            if best_match:
                tex_type, tex_info = best_match
                texture_info_list.append((tex_node, tex_type, tex_info))
                print(f"Texture identified: {tex_node.name} -> {tex_type}")
                
                if tex_type == 'ao':
                    ao_texture_node = tex_node
                elif tex_type == 'color':
                    color_texture_node = tex_node
                elif tex_type == 'orm':
                    orm_node = tex_node
                elif tex_type == 'ors':
                    ors_node = tex_node
            else:
                texture_info_list.append((tex_node, 'unassigned', {
                    'keywords': [],
                    'socket': None,
                    'priority': 0,
                    'is_unassigned': True
                }))
                print(f"Texture not identified, will be created but not connected: {tex_node.name}")
        
        texture_info_list.sort(key=lambda x: texture_mapping.get(x[1], {'priority': 0}).get('priority', 0), reverse=True)
        
        # Handle ORM and ORS textures first
        for tex_node, tex_type, tex_info in texture_info_list:
            if tex_type == 'orm':
                orm_ao_channel = self.setup_combined_texture(node_tree, material_node, tex_node, tex_type, mapping_node)
                if orm_ao_channel:
                    connected_count += 1
                    print(f"DEBUG: ORM texture configured, AO channel available")
            elif tex_type == 'ors':
                ors_ao_channel = self.setup_combined_texture(node_tree, material_node, tex_node, tex_type, mapping_node)
                if ors_ao_channel:
                    connected_count += 1
                    print(f"DEBUG: ORS texture configured, AO channel available")
        
        # Setup AO multiplication with Color
        ao_channel = None
        if ao_texture_node and hasattr(ao_texture_node, 'outputs') and len(ao_texture_node.outputs) > 0:
            # Connect mapping to AO texture
            if mapping_node and self.create_uv_node:
                self.connect_mapping_to_texture(node_tree, mapping_node, ao_texture_node)
            
            ao_output = None
            for output in ao_texture_node.outputs:
                if output.name.lower() in ['color', 'image', 'value']:
                    ao_output = output
                    break
            if not ao_output and len(ao_texture_node.outputs) > 0:
                ao_output = ao_texture_node.outputs[0]
            ao_channel = ao_output
        elif orm_ao_channel:
            ao_channel = orm_ao_channel
        elif ors_ao_channel:
            ao_channel = ors_ao_channel
        
        # Multiply AO with Color
        if ao_channel:
            print(f"DEBUG: Setting up AO multiplication with Base Color...")
            
            # Get the color texture to multiply with
            color_texture_for_ao = None
            if color_texture_node:
                color_texture_for_ao = color_texture_node
            else:
                # Look for any color texture in the node tree
                for node in node_tree.nodes:
                    if node.bl_idname in ['LuxCoreNodeTexImagemap', 'LuxCoreNodeTexImage', 'ShaderNodeTexImage']:
                        if node != ao_texture_node and node != orm_node and node != ors_node:
                            node_name = node.name.lower()
                            image_name = ""
                            if hasattr(node, 'image') and node.image:
                                image_name = node.image.name.lower()
                            
                            search_text = node_name + " " + image_name
                            color_keywords = ['color', 'diff', 'diffuse', 'albedo', 'basecolor', 'col', 'base']
                            for keyword in color_keywords:
                                pattern = r'(^|[^a-zA-Z0-9])' + re.escape(keyword) + r'($|[^a-zA-Z0-9])'
                                if re.search(pattern, search_text, re.IGNORECASE):
                                    color_texture_for_ao = node
                                    break
            
            # Connect mapping to color texture before multiplication
            if color_texture_for_ao and mapping_node and self.create_uv_node:
                self.connect_mapping_to_texture(node_tree, mapping_node, color_texture_for_ao)
            
            # Perform multiplication
            if self.multiply_ao_with_color(node_tree, material_node, color_texture_for_ao, ao_channel, 
                                           ao_texture_node or orm_node or ors_node):
                connected_count += 1
                print(f"DEBUG: AO multiplied with Color")
        elif color_texture_node:
            # Connect mapping to color texture first
            if mapping_node and self.create_uv_node:
                self.connect_mapping_to_texture(node_tree, mapping_node, color_texture_node)
            
            # Connect only color texture
            if hasattr(color_texture_node, 'outputs') and len(color_texture_node.outputs) > 0:
                color_output = None
                for output in color_texture_node.outputs:
                    if output.name.lower() in ['color', 'image', 'value']:
                        color_output = output
                        break
                if not color_output and len(color_texture_node.outputs) > 0:
                    color_output = color_texture_node.outputs[0]
                
                if color_output and 'Base Color' in material_node.inputs:
                    node_tree.links.new(color_output, material_node.inputs['Base Color'])
                    color_texture_node.label += " →Base Color"
                    connected_count += 1
        
        # Second pass: connect all other textures
        for tex_node, tex_type, tex_info in texture_info_list:
            # Skip already handled textures
            if tex_type in ['orm', 'ors', 'ao', 'color']:
                continue
            
            try:
                if mapping_node and self.create_uv_node:
                    self.connect_mapping_to_texture(node_tree, mapping_node, tex_node)
                
                # Handle emission (requires intermediate Emission node)
                if tex_type == 'emission':
                    if self.setup_emission(node_tree, material_node, tex_node):
                        connected_count += 1
                        tex_node.label = f"{tex_type.upper()}: {tex_node.label}"
                        print(f"Connected {tex_type} through Emission node")
                
                # Handle bump map (requires intermediate Bump node)
                elif tex_type == 'bump':
                    if self.setup_bump(node_tree, material_node, tex_node, mapping_node):
                        connected_count += 1
                        tex_node.label = f"{tex_type.upper()}: {tex_node.label}"
                        print(f"Connected {tex_type} through Bump node")
                
                # Handle normal map (with Normalmap checkbox)
                elif tex_type == 'normal':
                    if 'socket' in tex_info and tex_info['socket'] in material_node.inputs:
                        if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                            node_tree.links.new(tex_node.outputs[0], material_node.inputs[tex_info['socket']])
                            connected_count += 1
                            tex_node.label = f"{tex_type.upper()}: {tex_node.label}"
                            print(f"Connected {tex_type} to {tex_info['socket']}")
                            self.setup_normal_map_properties(tex_node)
                
                # Handle textures with defined sockets
                elif 'socket' in tex_info and tex_info['socket'] in material_node.inputs:
                    if hasattr(tex_node, 'outputs') and len(tex_node.outputs) > 0:
                        node_tree.links.new(tex_node.outputs[0], material_node.inputs[tex_info['socket']])
                        connected_count += 1
                        tex_node.label = f"{tex_type.upper()}: {tex_node.label}"
                        print(f"Connected {tex_type} to {tex_info['socket']}")
                
                # Handle height map
                elif tex_type == 'height':
                    self.setup_displacement(node_tree, material_node, tex_node, material_output)
                    connected_count += 1
                    tex_node.label = f"{tex_type.upper()}: {tex_node.label}"
                
                # Handle unassigned textures
                elif tex_type == 'unassigned':
                    tex_node.label = f"UNASSIGNED: {tex_node.label}"
                    print(f"Created unassigned texture node: {tex_node.name} (not connected)")
                    
            except Exception as e:
                print(f"Error connecting texture {tex_node.name}: {e}")
                import traceback
                traceback.print_exc()
        
        return connected_count
    
    def connect_mapping_to_texture(self, node_tree, mapping_node, tex_node):
        try:
            if hasattr(mapping_node, 'outputs') and len(mapping_node.outputs) > 0:
                if hasattr(tex_node, 'inputs') and len(tex_node.inputs) > 0:
                    for input_socket in tex_node.inputs:
                        input_name = input_socket.name.lower()
                        if 'color' not in input_name and 'value' not in input_name:
                            node_tree.links.new(mapping_node.outputs[0], input_socket)
                            tex_node.label = (tex_node.label or tex_node.name) + " [UV]"
                            return True
                    
                    node_tree.links.new(mapping_node.outputs[0], tex_node.inputs[0])
                    tex_node.label = (tex_node.label or tex_node.name) + " [UV]"
                    return True
        except Exception as e:
            print(f"Error connecting mapping: {str(e)}")
        
        return False
    
    def setup_emission(self, node_tree, material_node, tex_node):
        """Setup Emission texture through an intermediate Emission node"""
        try:
            # Create Emission node (LuxCoreNodeMatEmission)
            try:
                emission_node = node_tree.nodes.new(type='LuxCoreNodeMatEmission')
            except Exception as e:
                print(f"Cannot create Emission node: {e}")
                return False
            
            # Position Emission node between texture and material node
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
            
            # Connect Emission node to Emission pin of material node
            if hasattr(emission_node, 'outputs') and len(emission_node.outputs) > 0:
                emission_output = emission_node.outputs[0]
                
                # Find Emission input in material node
                if 'Emission' in material_node.inputs:
                    node_tree.links.new(emission_output, material_node.inputs['Emission'])
                    return True
                else:
                    # Try alternative names
                    for input_socket in material_node.inputs:
                        if 'emission' in input_socket.name.lower() or 'emit' in input_socket.name.lower():
                            node_tree.links.new(emission_output, input_socket)
                            return True
                    
                    print("Emission input not found in material node")
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
            # The mapping is already connected to the texture in connect_textures_to_material
            # before calling setup_bump, so we don't need to do it here
            
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
    
    def setup_combined_texture(self, node_tree, material_node, combined_node, tex_type, mapping_node=None):
        """Configure an ORM or ORS combined texture with channel splitting, returns AO output"""
        try:
            print(f"DEBUG: Configuring {tex_type} texture: {combined_node.name}")
            
            # Connect mapping to combined texture first
            if mapping_node and self.create_uv_node:
                self.connect_mapping_to_texture(node_tree, mapping_node, combined_node)
            
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
    
    def setup_displacement(self, node_tree, material_node, height_node, material_output):
        if not material_output:
            return
        
        try:
            displacement_height = 0.01
            
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
                displacement_node.height = displacement_height
            elif hasattr(displacement_node, 'value'):
                displacement_node.value = displacement_height
            
            if hasattr(displacement_node, 'scale'):
                displacement_node.scale = 0.02
                height_node.label = (height_node.label or height_node.name) + " [Scale:0.02]"
            
            # ENABLE SMOOTH NORMALS
            smooth_normals_props = ['normal_smooth', 'smooth_normals', 'smooth_normal', 'normal_smoothing']
            for prop_name in smooth_normals_props:
                if hasattr(displacement_node, prop_name):
                    try:
                        setattr(displacement_node, prop_name, True)
                        height_node.label += " [Smooth]"
                        print(f"DEBUG: Enabled smooth normals on {displacement_node.name}")
                        break
                    except (AttributeError, TypeError):
                        continue
            
            if hasattr(height_node, 'outputs') and len(height_node.outputs) > 0:
                if hasattr(displacement_node, 'inputs') and len(displacement_node.inputs) > 0:
                    height_input = None
                    for input_socket in displacement_node.inputs:
                        input_name = input_socket.name.lower()
                        if 'height' in input_name:
                            height_input = input_socket
                            break
                    
                    if not height_input:
                        height_input = displacement_node.inputs[0]
                    
                    node_tree.links.new(height_node.outputs[0], height_input)
                    height_node.label = (height_node.label or height_node.name) + " →Height"
            
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
                for input_socket in displacement_node.inputs:
                    input_name = input_socket.name
                    if input_name == 'Shape' or 'shape' in input_name.lower():
                        shape_input_disp = input_socket
                        break
                
                if shape_input_disp and hasattr(subdivision_node, 'outputs'):
                    shape_output_subdiv = None
                    for output_socket in subdivision_node.outputs:
                        output_name = output_socket.name
                        if output_name == 'Shape' or 'shape' in output_name.lower():
                            shape_output_subdiv = output_socket
                            break
                    if not shape_output_subdiv and len(subdivision_node.outputs) > 0:
                        shape_output_subdiv = subdivision_node.outputs[0]
                    
                    if shape_output_subdiv:
                        node_tree.links.new(shape_output_subdiv, shape_input_disp)
            
            if hasattr(displacement_node, 'outputs') and len(displacement_node.outputs) > 0:
                # Collega Height Displacement → Material Output
                if hasattr(material_output, 'inputs') and len(material_output.inputs) > 0:
                    shape_input = None
                    for input_socket in material_output.inputs:
                        input_name = input_socket.name.lower()
                        if 'shape' in input_name or 'displacement' in input_name:
                            shape_input = input_socket
                            break
                    
                    if shape_input:
                        shape_output = None
                        for output_socket in displacement_node.outputs:
                            output_name = output_socket.name.lower()
                            if 'shape' in output_name:
                                shape_output = output_socket
                                break
                        
                        if not shape_output:
                            shape_output = displacement_node.outputs[0]
                        
                        node_tree.links.new(shape_output, shape_input)
                        displacement_node.label = displacement_node.label + " →Shape"
            
        except Exception as e:
            print(f"Error setting up displacement: {str(e)}")
    
    def organize_nodes(self, node_tree, material_node, texture_nodes, mapping_node, material_output):
        material_node.location = (0, 0)
        
        if mapping_node:
            mapping_node.location = (-800, 0)
        
        x_start = -600
        y_start = 300
        
        for i, tex_node in enumerate(texture_nodes):
            tex_node.location = (x_start, y_start - i * 120)
        
        if material_output:
            material_output.location = (400, 0)
    
    def open_luxcore_node_editor(self, context, material):
        try:
            if context.active_object:
                context.active_object.active_material = material
            
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'NODE_EDITOR':
                        for space in area.spaces:
                            if space.type == 'NODE_EDITOR':
                                if hasattr(material, 'luxcore') and material.luxcore.node_tree:
                                    space.node_tree = material.luxcore.node_tree
                                else:
                                    space.node_tree = material.node_tree
                                area.tag_redraw()
                                return True
        except Exception as e:
            print(f"Error opening node editor: {e}")
        
        return False
    
    def refresh_ui(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

class LUXCORE_EXTRACT_OT_analyze_material(Operator):
    """Analyze active material and show found textures"""
    bl_idname = "luxcore_extract.analyze_material"
    bl_label = "Analyze Active Material Textures"
    
    @classmethod
    def poll(cls, context):
        return hasattr(context, 'material') and context.material is not None
    
    def execute(self, context):
        material = context.material
        
        if not material:
            self.report({'ERROR'}, "No material selected in Material Properties window")
            return {'CANCELLED'}
        
        print(f"=== LUXCORE EXTRACTOR: Analyzing textures of material '{material.name}' ===")
        textures = self.extract_textures_from_material(material)
        
        scene = context.scene
        if not hasattr(scene, 'luxcore_extract_texture_list'):
            scene.luxcore_extract_texture_list = []
        else:
            scene.luxcore_extract_texture_list.clear()
        
        for tex_info in textures:
            item = scene.luxcore_extract_texture_list.add()
            item.name = tex_info['name']
            item.connected = tex_info['is_connected']
            item.type = tex_info.get('type', 'IMAGE')
            item.filepath = tex_info.get('filepath', '')
        
        scene.luxcore_extract_analyzed_material = material.name
        
        self.report({'INFO'}, f"Found {len(textures)} textures in material '{material.name}'")
        return {'FINISHED'}
    
    def extract_textures_from_material(self, material):
        textures = []
        processed_images = set()
        
        if not material.use_nodes:
            print(f"Material '{material.name}' doesn't use nodes")
            return textures
        
        def explore_nodes(node_tree, tree_name="root"):
            for node in node_tree.nodes:
                if node.type == 'TEX_IMAGE' and node.image:
                    if node.image.name not in processed_images:
                        textures.append({
                            'name': node.image.name,
                            'is_connected': any(len(output.links) > 0 for output in node.outputs),
                            'type': 'IMAGE',
                            'filepath': node.image.filepath if node.image.filepath else node.image.name
                        })
                        processed_images.add(node.image.name)
                        print(f"Found texture: {node.image.name}")
                
                elif node.type == 'GROUP' and node.node_tree:
                    explore_nodes(node.node_tree, f"{tree_name} > {node.node_tree.name}")
                
                elif node.type == 'TEX_ENVIRONMENT' and node.image:
                    if node.image.name not in processed_images:
                        textures.append({
                            'name': node.image.name,
                            'is_connected': any(len(output.links) > 0 for output in node.outputs),
                            'type': 'ENVIRONMENT',
                            'filepath': node.image.filepath if node.image.filepath else node.image.name
                        })
                        processed_images.add(node.image.name)
                        print(f"Found environment texture: {node.image.name}")
        
        print(f"Exploring node tree of material '{material.name}'")
        explore_nodes(material.node_tree)
        return textures

class LUXCORE_EXTRACT_PT_material_panel(Panel):
    bl_label = "LuxCore Texture Extractor"
    bl_idname = "LUXCORE_EXTRACT_PT_material_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "material"
    bl_order = 1000
    
    def draw(self, context):
        layout = self.layout
        material = context.material
        
        if not material:
            layout.label(text="No material selected", icon='ERROR')
            return
        
        box = layout.box()
        row = box.row()
        row.label(text=f"Material: {material.name}", icon='MATERIAL_DATA')
        
        col = box.column(align=True)
        col.label(text="Analysis:", icon='VIEWZOOM')
        
        row = col.row(align=True)
        row.operator("luxcore_extract.analyze_material", text="Analyze Textures", icon='ZOOM_IN')
        
        scene = context.scene
        if hasattr(scene, 'luxcore_extract_analyzed_material') and scene.luxcore_extract_analyzed_material:
            if scene.luxcore_extract_analyzed_material == material.name:
                if hasattr(scene, 'luxcore_extract_texture_list') and scene.luxcore_extract_texture_list:
                    col = box.column(align=True)
                    col.label(text="Found Textures:", icon='TEXTURE')
                    
                    for i, item in enumerate(scene.luxcore_extract_texture_list):
                        row = col.row(align=True)
                        row.label(text=f"• {item.name}")
                        
                        if item.connected:
                            row.label(text="", icon='LINKED')
                        else:
                            row.label(text="", icon='UNLINKED')
        
        box = layout.box()
        box.label(text="Extraction to LuxCore:", icon='EXPORT')
        
        col = box.column(align=True)
        
        col.prop(context.scene, "luxcore_extract_only_used", text="Only Connected Textures")
        col.prop(context.scene, "luxcore_extract_create_material", text="Create LuxCore Disney Material")
        col.prop(context.scene, "luxcore_extract_auto_connect", text="Auto Connect")
        
        if context.scene.luxcore_extract_auto_connect:
            advanced_box = layout.box()
            advanced_box.label(text="Connection Options:", icon='SETTINGS')
            advanced_col = advanced_box.column(align=True)
            
            advanced_col.prop(context.scene, "luxcore_extract_create_uv_node", text="Create UV Node")
            advanced_col.prop(context.scene, "luxcore_extract_transfer_values", text="Transfer Principled Values")
            
            # Info about transferred values
            if context.scene.luxcore_extract_transfer_values:
                info_box = advanced_box.box()
                info_box.scale_y = 0.8
                info_col = info_box.column(align=True)
                info_col.label(text="Values transferred (if no texture):", icon='INFO')
                info_col.label(text="Base Color, Metallic, Roughness,")
                info_col.label(text="Specular, Sheen, Clearcoat, Opacity,")
                info_col.label(text="Emission Color")
        
        col.separator()
        
        op = col.operator("luxcore_extract.extract_textures", 
                         text="Extract Textures to LuxCore", 
                         icon='NODE_MATERIAL')
        op.only_used_textures = context.scene.luxcore_extract_only_used
        op.create_luxcore_material = context.scene.luxcore_extract_create_material
        op.auto_connect = context.scene.luxcore_extract_auto_connect
        
        if context.scene.luxcore_extract_auto_connect:
            op.create_uv_node = context.scene.luxcore_extract_create_uv_node
            op.transfer_principled_values = context.scene.luxcore_extract_transfer_values

class LuxCoreExtractTextureListItem(bpy.types.PropertyGroup):
    name: StringProperty(name="Texture Name")
    connected: BoolProperty(name="Connected")
    type: StringProperty(name="Type")
    filepath: StringProperty(name="Filepath")

def register():
    bpy.utils.register_class(LuxCoreExtractTextureListItem)
    
    bpy.types.Scene.luxcore_extract_only_used = BoolProperty(
        name="Only Used Textures",
        description="Extract only textures connected to material",
        default=True
    )
    
    bpy.types.Scene.luxcore_extract_create_material = BoolProperty(
        name="Create LuxCore Material",
        description="Automatically create a LuxCore Disney material",
        default=True
    )
    
    bpy.types.Scene.luxcore_extract_auto_connect = BoolProperty(
        name="Auto Connect Textures",
        description="Automatically connect textures to Disney material",
        default=True
    )
    
    bpy.types.Scene.luxcore_extract_create_uv_node = BoolProperty(
        name="Create UV Node",
        description="Create a shared 2D Mapping node for all textures",
        default=True,
    )
    
    bpy.types.Scene.luxcore_extract_transfer_values = BoolProperty(
        name="Transfer Principled Values",
        description="Transfer numeric values from Principled BSDF to Disney node (Base Color, Metallic, Roughness, etc.)",
        default=True,
    )
    
    bpy.types.Scene.luxcore_extract_texture_list = CollectionProperty(type=LuxCoreExtractTextureListItem)
    
    bpy.types.Scene.luxcore_extract_analyzed_material = StringProperty(
        name="Analyzed Material",
        description="Name of most recently analyzed material",
        default=""
    )
    
    bpy.utils.register_class(LUXCORE_EXTRACT_OT_extract_textures)
    bpy.utils.register_class(LUXCORE_EXTRACT_OT_analyze_material)
    bpy.utils.register_class(LUXCORE_EXTRACT_PT_material_panel)

def unregister():
    bpy.utils.unregister_class(LUXCORE_EXTRACT_OT_extract_textures)
    bpy.utils.unregister_class(LUXCORE_EXTRACT_OT_analyze_material)
    bpy.utils.unregister_class(LUXCORE_EXTRACT_PT_material_panel)
    
    bpy.utils.unregister_class(LuxCoreExtractTextureListItem)
    
    del bpy.types.Scene.luxcore_extract_only_used
    del bpy.types.Scene.luxcore_extract_create_material
    del bpy.types.Scene.luxcore_extract_auto_connect
    del bpy.types.Scene.luxcore_extract_create_uv_node
    del bpy.types.Scene.luxcore_extract_transfer_values
    del bpy.types.Scene.luxcore_extract_texture_list
    del bpy.types.Scene.luxcore_extract_analyzed_material

if __name__ == "__main__":
    register()
