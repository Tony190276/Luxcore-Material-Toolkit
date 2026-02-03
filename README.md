Automatically recognize the most common Blender PBR texture naming conventions
(BaseColor / Albedo, Normal, Roughness, Metallic, Specular, Height / Displacement, AO, Emission, etc.)
and connect them to the correct inputs of the Disney node
Create necessary intermediate nodes when needed (for example: Height → Displacement node, or color correction Multiply / Mix nodes)
Convert an existing Cycles PBR material by scanning the used textures and reconnecting everything properly to the Disney node
Connect PBR textures with one single click directly from the LuxCore Material Nodes editor

The main goal is to save a huge amount of time when working with the many free / paid PBR material libraries available online, or when you need to convert materials already present in your scene.
This is particularly helpful in architectural visualization projects, where you often have dozens (or hundreds) of materials and the manual setup becomes really time-consuming — frequently pushing people to fall back to Cycles or Eevee instead of LuxCore.
The add-on is really simple and intuitive to use and, in any case, I’ve made a short video where I quickly explain all the main functions and show it in action.
I would really appreciate any kind of feedback, bug reports, suggestions or ideas from the community to make it even better.
If there’s enough interest I’m also happy to create a proper GitHub repository and release it properly.
So far it has been tested with:

LuxCore 2.10
Blender 4.2 / 4.5 / 5.0.1
Linux and Windows
