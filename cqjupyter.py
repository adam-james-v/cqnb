import cadquery as cq
from cadquery import cqgi, exporters
from IPython.display import display
import pythreejs
import numpy as np
import matplotlib
import sys, os, StringIO, json
import ipywidgets

# TODO: rename and re-organize functions
# TODO: save into cqnb folder
# TODO: figure out how to propery do install (adding cqnb_start.py to the startup folder seems incorrect)

# The following bits are just to block print output while CQGI parses script
# Without using these, it might print 'unable to handle function' multiple times, which clutters the output space
# save ref to IPython stdout so that it can be restored if switched away from
nb_stdout = sys.stdout

# Disable
def blockPrint():
    sys.stdout = open(os.devnull, 'w')

# Restore
def enablePrint():
    sys.stdout = nb_stdout


# This Module expects a cadquery object

def cqdisplay(result, color='#708090', cam_dist=50, fov=35, display_id=None):

    # Open stream
    output = StringIO.StringIO()

    # cadquery will stream a ThreeJS JSON (using old v3 schema, which is deprecated)
    exporters.exportShape(result, 'TJS', output)

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

    # Cadquery does not supply face normals in the JSON, and we cannot use THREE.JS built in 'computeFaceNormals' -- at least not easily
    # Instead, we just calculate the face normals ourselves. It is just the cross product of 2 vectors in the triangle.
    # TODO: see if there is a better way to achieve this result
    faceNormals = []

    for entry in faces:
        vA = np.asarray(vertices[entry[0]])
        vB = np.asarray(vertices[entry[1]])
        vC = np.asarray(vertices[entry[2]])

        vecA = vB - vA
        vecB = vC - vA

        cross = np.cross(vecA, vecB)

        faceNormals.append([cross[0], cross[1], cross[2]])

    # set up geometry
    geom = pythreejs.PlainGeometry(vertices=vertices, faces=faces, faceNormals=faceNormals)
    mtl = pythreejs.LambertMaterial(color = color, shading = 'FlatShading')
    obj = pythreejs.Mesh(geometry=geom, material = mtl)

    # set up scene and camera
    cam = pythreejs.PerspectiveCamera(
        position=[cam_dist, cam_dist, cam_dist], fov=fov,
        children=[pythreejs.DirectionalLight(color='#ffffff', position=[-3, 5, 1], intensity=0.45)])
    scn_chld = [
        obj,
        pythreejs.AmbientLight(color='#dddddd')
    ]
    scn = pythreejs.Scene(children=scn_chld)

    render = pythreejs.Renderer(camera=cam, scene = scn, controls=[pythreejs.OrbitControls(controlling=cam)])

    return render


def build_object(result):
    # Get the Script's text from the IPython shell's history
    # TODO: sanitizing function that removes dangerous imports. Eg. strip any lines that have 'import cqjupyter'
    # luckily, the cell which has just been run by user is immediately placed as the latest entry in the history
    scriptText = get_ipython().history_manager.input_hist_raw[-1]

    # A representation of the CQ script with all the metadata attached
    # stop parse func from printing to the shell. Do this to avoid excessive 'unable to handle function call' warnings
    # TODO: fix this the real way... find out proper way to handle this from CQGI author
    blockPrint()
    cqModel = cqgi.parse(scriptText)
    # re-enable printing to shell
    enablePrint()

    build_result = cqModel.build()

    # function that creates and updates the model view along with param. interactions
    # kwargs is built up in a loop over the parameters which CQGI supplies
    def f(**kwargs):
        new_vals = {}
        # kwargs is linked to ipywidget interactive vals
        # set the kwarg's name as key, set kwarg's value as value.
        # pass new vals as dict into update_build so that CQGI processes the model with
        # the values that the user has input into the interactive boxes
        for arg in kwargs:
            new_vals[arg] = kwargs[arg]
        try:
            f.base.close()
        except:
            pass
        f.base = update_build(cqModel, new_vals)
        display(f.base)
    f.base = None

    # Make sure that the build was successful
    if build_result.success:
        # Allows us to present parameters for editing throuhg some interface
        params = cqModel.metadata.parameters
        interactions = cq_interact(params)

        # Display all the results that the user requested
        for result in build_result.results:
            # Render the solid and its parameter interactions
            ipywidgets.interact_manual(f, **cq_interact(params));
        return
    else:
        print "Error executing CQGI-compliant script."

def cq_interact(params):
    interactions = {}
    for key in params:
        name = params[key].name
        val = params[key].default_value
        if type(val) is int:
            interactions[name] = ipywidgets.IntText(description=name, value=val, continuous_update=False)
        elif type(val) is float:
            interactions[name] = ipywidgets.FloatText(description=name, value=val, continuous_update=False)
        elif type(val) is bool:
            interactions[name] = ipywidgets.Checkbox(description=name, value=val, continuous_update=False)
        else:
            interactions[name] = ipywidgets.Text(description=name, value=val, continuous_update=False)
    return interactions

def update_build(model, build_parameters, build_options=None):
    build_result = model.build(build_parameters=build_parameters, build_options=build_options)
    if build_result.success:
        # TODO: fix this for loop. I'm returning in there... so only need to grab 1 entry from the list.
        # NOTE: I don't know why there is a list or under what circumstances there will be more than 1 entry
        # whatever the case is, this for loop won't handle that scenario properly yet
        for result in build_result.results:
            # Render the solid
            render = cqdisplay(result)
            return render