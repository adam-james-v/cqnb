"""
    Jupyter Extension for cadquery script evaluation and display

    The goal of this extension is to allow cadquery to be used easily and
    reliably within Jupyter Notebooks. It aims to keep feature parity with
    the Cadquery FreeCAD implementation, and seeks to be one of the main
    alternative GUIs that cadquery users can rely on for day-to-day CQ use.abs

    For further resources on cadquery, see https://github.com/dcowden/cadquery
"""


import sys
import os
import StringIO
import json
import cadquery as cq
from cadquery import cqgi, exporters
from IPython.display import display
import pythreejs
import numpy as np
import matplotlib
import matplotlib.colors as colors
import ipywidgets

# TODO: rename and re-organize functions
# TODO: save into cqnb folder
# TODO: figure out how to properly do Extension installation

# The following bits are just to block print output while CQGI parses script
# Make block/enable print  functions to hide excessive stdout writes from CQGI
# save ref to IPython stdout so that it can be restored if switched away from
NB_STDOUT = sys.stdout
# Disable
def block_print():
    'block stdout'
    sys.stdout = open(os.devnull, 'w')

# Restore
def enable_print():
    'enable stdout'
    sys.stdout = NB_STDOUT


# This Module expects a cadquery object

def cqdisplay(result, color='#708090', scale=1.0):
    'display CQ object in a ThreeJS Webgl context'
    # Open stream
    output = StringIO.StringIO()

    # cadquery will stream a ThreeJS JSON (using old v3 schema, which is deprecated)
    exporters.exportShape(result.shape.findSolid().scale(scale), 'TJS', output)

    # store stream to a variable
    contents = output.getvalue()

    # Close stream
    output.close()

    # Overwrite the JSON color portion with user defined color. Disallows NAMED colors
    col = list(matplotlib.colors.hex2color(color))
    old_col_str = '"colorDiffuse" : [0.6400000190734865, 0.10179081114814892, 0.126246120426746]'
    new_col_str = '"colorDiffuse" : ' + str(col)
    new_contents = contents.replace(old_col_str, new_col_str)

    # Take the string and create a proper json object
    contents = json.loads(contents)

    # Vertices and Faces are both flat lists, but the pythreejs module requires list of lists
    old_v = contents['vertices']
    old_f = contents['faces']

    # Splits the list up in 3s, to produce a list of lists representing the vertices
    vertices = [old_v[i:i+3] for i in range(0, len(old_v), 3)]

    # JSON Schema has first position in the face's list reserved to indicate type.
    # Cadquery returns Triangle mesh, so we know that we must split list into lists of length 4
    # 1st entry to indicate triangle, next 3 to specify vertices
    three_faces = [old_f[i:i+4] for i in range(0, len(old_f), 4)]
    faces = []

    # Drop the first entry in the face list
    for entry in three_faces:
        entry.pop(0)
        faces.append(entry)

    # Cadquery does not supply face normals in the JSON,
    # and we cannot use THREE.JS built in 'computefaceNormals'
    # (at least, not easily)
    # Instead, we just calculate the face normals ourselves.
    # It is just the cross product of 2 vectors in the triangle.
    # TODO: see if there is a better way to achieve this result
    face_normals = []

    for entry in faces:
        v_a = np.asarray(vertices[entry[0]])
        v_b = np.asarray(vertices[entry[1]])
        v_c = np.asarray(vertices[entry[2]])

        vec_a = v_b - v_a
        vec_b = v_c - v_a

        cross = np.cross(vec_a, vec_b)

        face_normals.append([cross[0], cross[1], cross[2]])

    # set up geometry
    geom = pythreejs.PlainGeometry(vertices=vertices, faces=faces, faceNormals=face_normals)
    mtl = pythreejs.LambertMaterial(color=color, shading='FlatShading')
    obj = pythreejs.Mesh(geometry=geom, material=mtl)

    # set up scene and camera
    cam_dist = 50
    fov = 35
    cam = pythreejs.PerspectiveCamera(
        position=[cam_dist, cam_dist, cam_dist], fov=fov,
        children=[pythreejs.DirectionalLight(color='#ffffff', position=[-3, 5, 1], intensity=0.45)])
    scn_chld = [
        obj,
        pythreejs.AmbientLight(color='#dddddd')
    ]
    scn = pythreejs.Scene(children=scn_chld)

    render = pythreejs.Renderer(
        width='830'.decode('utf-8'),
        height='553'.decode('utf-8'),
        camera=cam,
        scene=scn,
        controls=[pythreejs.OrbitControls(controlling=cam)]
        )

    return render

def cqgen(result, name='Output', color='#708090'):
    'generate a .JSON file for ThreeJS objects.'
    # Open stream
    output = StringIO.StringIO()

    # cadquery will stream a ThreeJS JSON (using old v3 schema, which is deprecated)
    exporters.exportShape(result, 'TJS', output)

    # store stream to a variable
    contents = output.getvalue()

    # Close stream
    output.close()

    # Overwrite the JSON color portion with user color. Disallows NAMED colors
    col = list(colors.hex2color(color))
    old_col_str = '"colorDiffuse" : [0.6400000190734865, 0.10179081114814892, 0.126246120426746]'
    new_col_str = '"colorDiffuse" : ' + str(col)
    new_contents = contents.replace(old_col_str, new_col_str)


    file_name = name + '.json'
    # Save the string to a json file
    with open(file_name, "w") as text_file:
        text_file.write(new_contents)

    # print "Part generated : " + file_name

    return


def show_object(result):
    'returns an object to the Jupyter Widgets area with interactive options'
    # Get the Script's text from the IPython shell's history
    # TODO: sanitizing function that removes dangerous imports.
    # Eg. strip any lines that have 'import cqjupyter'
    # luckily, the cell which has just been run by user
    # is immediately placed as the latest entry in the history
    script_text = get_ipython().history_manager.input_hist_raw[-1]

    def find_between(src, first, last):
        'returns string between two specified substrings'
        # credit: https://stackoverflow.com/a/3368991
        try:
            start = src.index(first) + len(first)
            end = src.index(last, start)
            return src[start:end]
        except ValueError:
            return ""

    obj_name = find_between(script_text, 'show_object(', ')')

    # A representation of the CQ script with all the metadata attached
    # stop parse func from printing to the shell to avoid excessive warnings
    # TODO: fix this the real way... find out proper way to handle this from CQGI author
    block_print()
    # change show_object() to build_object until I have opportunity to update CQ...
    # script_text = script_text.replace('show_object(', 'build_object(')
    cq_model = cqgi.parse(script_text)
    # re-enable printing to shell
    enable_print()

    build_result = cq_model.build()

    # function that creates and updates the model view along with param. interactions
    # kwargs is built up in a loop over the parameters which CQGI supplies
    def mkui(**kwargs):
        'assembles widgets area according to parameters found in parsed script'
        new_vals = {}
        # kwargs is linked to ipywidget interactive vals
        # set the kwarg's name as key, set kwarg's value as value.
        # pass new vals as dict into update_build so that CQGI processes the model with
        # the values that the user has input into the interactive boxes
        for arg in kwargs:
            new_vals[arg] = kwargs[arg]
        try:
            mkui.base.close()
            mkui.export_filename.close()
            mkui.export_filetype.close()
            mkui.export_button.close()
        except AttributeError:
            pass
        color = mkui.display_options['display_color'].value
        units = mkui.display_options['display_units'].value
        scale = mkui.display_options['display_scale'].value

        if units == 'in':
            final_scale = scale*25.4
        else:
            final_scale = scale

        mkui.base, mkui.new_model = update_build(cq_model, new_vals, color=color, scale=final_scale)

        # Create the Export options + Button
        mkui.export_filename = ipywidgets.Text(
            description='Filename',
            value=obj_name,
            continuous_update=False
            )
        mkui.export_filetype = ipywidgets.Dropdown(
            description='Filetype',
            options=['STEP', 'JSON', 'STL', 'SVG'],
            value='STEP',
            continuous_update=False
            )

        def export_function(button):
            'executes export of user selected filetype, only on button press'
            filename = mkui.export_filename.value
            filetype = mkui.export_filetype.value
            fullname = filename + '.' + filetype
            if filetype == 'STEP':
                mkui.new_model.shape.findSolid().scale(final_scale).exportStep(fullname)
            if filetype == 'STL':
                mkui.new_model.shape.findSolid().scale(final_scale).wrapped.exportStl(fullname)
            elif filetype == 'JSON':
                cqgen(mkui.new_model.shape.findSolid().scale(final_scale), name=filename)
            elif filetype == 'SVG':
                cq.CQ(mkui.new_model.shape.findSolid().scale(final_scale)).exportSvg(fullname)
            else:
                print 'nothing exported, sorry'
            print 'exported model as: ' + fullname

        gui_layout = ipywidgets.Layout(
            display='flex',
            justify_content='center',
            align_items='center',
            max_width='30%',
        )
        options_layout = ipywidgets.Layout(
            max_width='50%',
        )

        mkui.export_button = ipywidgets.Button(description='Export', continuous_update=False)
        mkui.export_button.on_click(export_function)
        export_gui = ipywidgets.HBox([
            ipywidgets.VBox([mkui.export_filename, mkui.export_filetype]),
            mkui.export_button
            ])

        render_window = ipywidgets.VBox([mkui.base, export_gui])
        display(render_window)

    mkui.base = None
    mkui.export_filename = None
    mkui.export_filetype = None
    mkui.export_button = None

    # Make sure that the build was successful
    if build_result.success:
        # Allows us to present parameters for editing through some interface
        params = cq_model.metadata.parameters
        interactions, mkui.display_options = cq_interact(params)
        # Display all the results that the user requested
        # for result in build_result.results:
        # Render the solid and its parameter interactions
        # display(mkui.display_options)
        display(mkui.display_options['display_color'])
        display(mkui.display_options['display_units'])
        display(mkui.display_options['display_scale'])
        ipywidgets.interact_manual(mkui, **interactions)
        return
    else:
        print "Error executing CQGI-compliant script."

def cq_interact(params):
    'builds dict of interaction widgets for each exposed parameter'
    interactions = {}
    display_options = {}
    for key in params:
        name = params[key].name
        val = params[key].default_value
        if isinstance(val, int):
            if isinstance(val, bool):
                interactions[name] = ipywidgets.Checkbox(
                    description=name,
                    value=val,
                    continuous_update=False
                    )
            else:
                interactions[name] = ipywidgets.IntText(
                    description=name,
                    value=val,
                    continuous_update=False
                    )
        elif isinstance(val, float):
            interactions[name] = ipywidgets.FloatText(
                description=name,
                value=val,
                continuous_update=False
                )
        else:
            interactions[name] = ipywidgets.Text(
                description=name,
                value=val,
                continuous_update=False
                )

    # add color, units, scale selection
    display_options['display_color'] = ipywidgets.ColorPicker(
        description='Color: ',
        value='#8dc63f',
        concise=False,
        continuous_update=False
        )
    display_options['display_units'] = ipywidgets.ToggleButtons(
        description='Units: ',
        options=['mm', 'in'],
        value='mm',
        continuous_update=False
        )
    display_options['display_scale'] = ipywidgets.FloatText(
        description='Scale: ',
        value=1.0,
        continuous_update=False
        )

    return interactions, display_options

def update_build(model, build_parameters, build_options=None, color="#708090", scale=1.0):
    'updates an object given new parameter values from Jupyter widgets'
    build_result = model.build(build_parameters=build_parameters, build_options=build_options)
    if build_result.success:
        # TODO: fix this for loop.
        # whatever the case is, this for loop won't handle that scenario properly yet
        for result in build_result.results:
            # Render the solid
            render = cqdisplay(result, color=color, scale=scale)
            return render, result
