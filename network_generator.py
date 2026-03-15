import os
import random
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom

def generate_network():
    print("Generating network nodes and edges...")

    # Configuration for the grid
    GRID_SPACING = 75  # Base distance between junctions in meters
    JITTER = 40         # Maximum random offset to make road lengths non-uniform

    # 1. GENERATE NODES (grid.nod.xml)
    nodes_root = ET.Element("nodes")
    
    # Generate the 9 core junctions (3x3 grid)
    core_nodes =[]
    for row in range(3):
        for col in range(3):
            node_id = f"J{row * 3 + col}"
            
            # Base coordinates
            base_x = col * GRID_SPACING
            base_y = (2 - row) * GRID_SPACING # Invert Y so J0 is top-left
            
            # Add randomness to make road lengths different
            if node_id != "J4":
                x = base_x + random.randint(-JITTER, JITTER)
                y = base_y + random.randint(-JITTER, JITTER)
            else:
                x, y = base_x, base_y

            core_nodes.append((node_id, x, y))
            ET.SubElement(nodes_root, "node", id=node_id, x=str(x), y=str(y), type="traffic_light")

    # Generate the 4 corner "dead end" entry/exit points
    corner_spawns = {
        "N_NW": (-GRID_SPACING + random.randint(-JITTER, 0), 3 * GRID_SPACING + random.randint(0, JITTER)),
        "N_NE": (3 * GRID_SPACING + random.randint(0, JITTER), 3 * GRID_SPACING + random.randint(0, JITTER)),
        "N_SW": (-GRID_SPACING + random.randint(-JITTER, 0), -GRID_SPACING + random.randint(-JITTER, 0)),
        "N_SE": (3 * GRID_SPACING + random.randint(0, JITTER), -GRID_SPACING + random.randint(-JITTER, 0))
    }

    for n_id, (x, y) in corner_spawns.items():
        ET.SubElement(nodes_root, "node", id=n_id, x=str(x), y=str(y), type="priority")

    # Save Nodes XML
    xml_str = minidom.parseString(ET.tostring(nodes_root)).toprettyxml(indent="    ")
    with open("grid.nod.xml", "w") as f:
        f.write(xml_str)
    print("Created grid.nod.xml")

    # 2. GENERATE EDGES (grid.edg.xml)
    edges_root = ET.Element("edges")

    def add_bidirectional_road(edge_id_base, node_a, node_b):
        # 4 lanes total: 2 lanes in each direction
        # Forward edge (A to B) - Using a dictionary to bypass Python's 'from' keyword restriction
        ET.SubElement(edges_root, "edge", {
            "id": f"{edge_id_base}_A", 
            "from": node_a, 
            "to": node_b, 
            "numLanes": "2"
        })
        # Backward edge (B to A)
        ET.SubElement(edges_root, "edge", {
            "id": f"{edge_id_base}_B", 
            "from": node_b, 
            "to": node_a, 
            "numLanes": "2"
        })

    # Internal 3x3 Connections (Horizontal & Vertical)
    internal_connections =[
        ("E_J0_J1", "J0", "J1"), ("E_J1_J2", "J1", "J2"), # Top row
        ("E_J3_J4", "J3", "J4"), ("E_J4_J5", "J4", "J5"), # Middle row
        ("E_J6_J7", "J6", "J7"), ("E_J7_J8", "J7", "J8"), # Bottom row
        ("E_J0_J3", "J0", "J3"), ("E_J3_J6", "J3", "J6"), # Left col
        ("E_J1_J4", "J1", "J4"), ("E_J4_J7", "J4", "J7"), # Middle col
        ("E_J2_J5", "J2", "J5"), ("E_J5_J8", "J5", "J8")  # Right col
    ]
    for edge_id, frm, to in internal_connections:
        add_bidirectional_road(edge_id, frm, to)

    # External Connections (Corners to their respective Dead Ends)
    external_connections =[
        ("E_NW", "N_NW", "J0"),
        ("E_NE", "N_NE", "J2"),
        ("E_SW", "N_SW", "J6"),
        ("E_SE", "N_SE", "J8")
    ]
    for edge_id, frm, to in external_connections:
        add_bidirectional_road(edge_id, frm, to)

    # Save Edges XML
    xml_str = minidom.parseString(ET.tostring(edges_root)).toprettyxml(indent="    ")
    with open("grid.edg.xml", "w") as f:
        f.write(xml_str)
    print("Created grid.edg.xml")

    # 3. RUN NETCONVERT TO COMPILE THE NETWORK
    print("\nRunning SUMO netconvert...")
    netconvert_cmd =[
        "netconvert",
        "--node-files", "grid.nod.xml",
        "--edge-files", "grid.edg.xml",
        "--output-file", "grid.net.xml",
        "--no-turnarounds", "true",
        "--default.lanewidth", "4.0"
    ]
    
    try:
        subprocess.run(netconvert_cmd, check=True)
        print("Successfully generated 'grid.net.xml'!")
    except FileNotFoundError:
        print("ERROR: 'netconvert' command not found. Please ensure SUMO is installed and added to your system's PATH.")
    except subprocess.CalledProcessError as e:
        print(f"ERROR: netconvert failed with exit code {e.returncode}")

if __name__ == "__main__":
    generate_network()