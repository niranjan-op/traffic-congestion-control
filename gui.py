import tkinter as tk
from tkinter import ttk, messagebox
import xml.etree.ElementTree as ET
from xml.dom import minidom
import subprocess
import os
import random

# Map human-readable locations to the exact Edge IDs we generated
ORIGINS = {
    "North-West": "E_NW_A",
    "North-East": "E_NE_A",
    "South-West": "E_SW_A",
    "South-East": "E_SE_A"
}

DESTINATIONS = {
    "North-West": "E_NW_B",
    "North-East": "E_NE_B",
    "South-West": "E_SW_B",
    "South-East": "E_SE_B"
}

class SumoSpawnerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SUMO Traffic Spawner")
        self.root.geometry("450x550")
        
        self.trips_data =[] # Stores all configured routes
        
        self.create_widgets()

    def create_widgets(self):
        # --- Route Selection ---
        route_frame = ttk.LabelFrame(self.root, text="1. Select Route", padding=10)
        route_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(route_frame, text="Start Node (Origin):").grid(row=0, column=0, sticky="w")
        self.var_origin = tk.StringVar(value="North-West")
        self.drop_origin = ttk.Combobox(route_frame, textvariable=self.var_origin, values=list(ORIGINS.keys()), state="readonly")
        self.drop_origin.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(route_frame, text="End Node (Destination):").grid(row=1, column=0, sticky="w")
        self.var_dest = tk.StringVar(value="South-East")
        self.drop_dest = ttk.Combobox(route_frame, textvariable=self.var_dest, values=list(DESTINATIONS.keys()), state="readonly")
        self.drop_dest.grid(row=1, column=1, padx=5, pady=5)

        # --- Vehicle Quantities ---
        veh_frame = ttk.LabelFrame(self.root, text="2. Spawn Vehicles", padding=10)
        veh_frame.pack(fill="x", padx=10, pady=5)

        self.veh_vars = {}
        vehicles = ["Bikes", "Cars", "Ambulances", "Buses", "Trucks"]
        for i, v in enumerate(vehicles):
            ttk.Label(veh_frame, text=v + ":").grid(row=i, column=0, sticky="w")
            var = tk.IntVar(value=0)
            self.veh_vars[v.lower()[:-1] if v != "Buses" else "bus"] = var # maps to 'bike', 'car', 'ambulance', 'bus', 'truck'
            ttk.Entry(veh_frame, textvariable=var, width=10).grid(row=i, column=1, padx=5, pady=2)

        # --- Add Button ---
        ttk.Button(self.root, text="Add Route & Vehicles", command=self.add_route).pack(pady=5)

        # --- Active Routes List ---
        list_frame = ttk.LabelFrame(self.root, text="3. Configured Routes", padding=10)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.listbox = tk.Listbox(list_frame, height=6)
        self.listbox.pack(fill="both", expand=True)

        # --- Start Button ---
        start_btn = tk.Button(self.root, text="START SIMULATION", bg="green", fg="white", font=("Arial", 12, "bold"), command=self.start_simulation)
        start_btn.pack(fill="x", padx=10, pady=10)

    def add_route(self):
        orig_name = self.var_origin.get()
        dest_name = self.var_dest.get()
        
        if orig_name == dest_name:
            messagebox.showerror("Error", "Origin and Destination cannot be the same corner!")
            return

        # Gather counts
        counts = {v_type: var.get() for v_type, var in self.veh_vars.items() if var.get() > 0}
        
        if not counts:
            messagebox.showerror("Error", "Please add at least 1 vehicle!")
            return

        route_info = {
            "origin": ORIGINS[orig_name],
            "dest": DESTINATIONS[dest_name],
            "counts": counts
        }
        
        self.trips_data.append(route_info)
        
        # Display in listbox
        display_str = f"[{orig_name} -> {dest_name}] | " + ", ".join([f"{c} {v}" for v, c in counts.items()])
        self.listbox.insert(tk.END, display_str)
        
        # Reset vehicle entries to 0
        for var in self.veh_vars.values():
            var.set(0)

    def start_simulation(self):
        if not self.trips_data:
            messagebox.showerror("Error", "Please add at least one route before starting!")
            return

        self.generate_sumo_files()
        
        # Launch runner.py using subprocess so the GUI doesn't freeze
        print("Launching simulation...")
        subprocess.Popen(["python", "runner.py"])

    def generate_sumo_files(self):
        # 1. GENERATE routes.rou.xml
        routes_root = ET.Element("routes")
        
        all_trips =[]
        vehicle_id_counter = 0
        depart_times = {edge: 0.0 for edge in ORIGINS.values()}

        # --- NEW LOGIC FOR INTERMINGLED SPAWNING ---
        for route in self.trips_data:
            orig_edge = route["origin"]
            
            # Create one big list of all vehicles for this specific route
            vehicles_to_spawn_on_route = []
            for v_type, count in route["counts"].items():
                vehicles_to_spawn_on_route.extend([v_type] * count)
            
            # Shuffle the list to mix vehicle types randomly
            random.shuffle(vehicles_to_spawn_on_route)
            
            # Now generate trips from the shuffled, intermingled list
            for v_type in vehicles_to_spawn_on_route:
                start_speed_ms = round(random.uniform(4.17, 12.5), 2)
                
                trip_data = {
                    "id": f"{v_type}_{vehicle_id_counter}",
                    "type": v_type,
                    "depart": depart_times[orig_edge],
                    "from": orig_edge,
                    "to": route["dest"],
                    "departLane": "random",
                    "departSpeed": str(start_speed_ms)
                }
                all_trips.append(trip_data)
                
                vehicle_id_counter += 1
                depart_times[orig_edge] += 2.0 # Keep safe spacing

        # --- END OF NEW LOGIC ---

        # SORT ALL TRIPS from all routes by depart time
        all_trips.sort(key=lambda x: x["depart"])

        # Write sorted trips to XML
        for trip in all_trips:
            trip["depart"] = str(round(trip["depart"], 1))
            ET.SubElement(routes_root, "trip", trip)

        xml_str = minidom.parseString(ET.tostring(routes_root)).toprettyxml(indent="    ")
        with open("routes.rou.xml", "w") as f:
            f.write(xml_str)
        print("Generated routes.rou.xml")

        # 2. GENERATE sim.sumocfg
        config_root = ET.Element("configuration")
        input_elem = ET.SubElement(config_root, "input")
        
        ET.SubElement(input_elem, "net-file", value="grid.net.xml")
        ET.SubElement(input_elem, "route-files", value="routes.rou.xml")
        ET.SubElement(input_elem, "additional-files", value="vtypes.add.xml")
        
        proc_elem = ET.SubElement(config_root, "processing")
        ET.SubElement(proc_elem, "ignore-route-errors", value="true")
        ET.SubElement(proc_elem, "collision.action", value="warn")
        
        xml_str = minidom.parseString(ET.tostring(config_root)).toprettyxml(indent="    ")
        with open("sim.sumocfg", "w") as f:
            f.write(xml_str)
        print("Generated sim.sumocfg")

if __name__ == "__main__":
    root = tk.Tk()
    app = SumoSpawnerGUI(root)
    root.mainloop()