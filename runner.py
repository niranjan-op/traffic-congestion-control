import traci
import sumolib
import math
import collections

class JunctionWorker:
    def __init__(self, tls_id, net):
        self.tls_id = tls_id
        self.node = net.getNode(tls_id)
        
        self.incoming_edges =[e.getID() for e in self.node.getIncoming()]
        self.outgoing_edges =[e.getID() for e in self.node.getOutgoing()]
        
        self.edge_to_links = {}
        self.link_targets = {}
        links = traci.trafficlight.getControlledLinks(tls_id)
        self.num_links = len(links)
        
        for i, link_info in enumerate(links):
            if link_info:
                from_lane = link_info[0][0]
                to_lane = link_info[0][1]
                from_edge = traci.lane.getEdgeID(from_lane)
                to_edge = traci.lane.getEdgeID(to_lane)
                
                if from_edge not in self.edge_to_links:
                    self.edge_to_links[from_edge] = []
                self.edge_to_links[from_edge].append(i)
                self.link_targets[i] = to_edge
                
        self.controlled_edges = list(self.edge_to_links.keys())
        
        self.edge_lengths = {}
        for edge in self.controlled_edges:
            self.edge_lengths[edge] = net.getEdge(edge).getLength()
        
        self.current_green_edge = self.controlled_edges[0] if self.controlled_edges else None
        self.state = "GREEN"
        self.timer = 0
        self.next_green_edge = None

    def set_light(self, target_edge, color):
        state_list = ['r'] * self.num_links
        if target_edge in self.edge_to_links:
            for idx in self.edge_to_links[target_edge]:
                if color == 'G':
                    target_out_edge = self.link_targets.get(idx)
                    is_blocked = False
                    if target_out_edge:
                        try:
                            if traci.edge.getLastStepOccupancy(target_out_edge) > 0.82:
                                is_blocked = True
                        except: pass
                    state_list[idx] = 'r' if is_blocked else 'G'
                elif color == 'y':
                    state_list[idx] = 'y'
                else:
                    state_list[idx] = 'r'
        traci.trafficlight.setRedYellowGreenState(self.tls_id, "".join(state_list))

    def calculate_scores(self, global_scores):
        scores = {}
        for edge in self.controlled_edges:
            veh_ids = traci.edge.getLastStepVehicleIDs(edge)
            w_normal = 0
            w_emergency = 0
            density = 0
            
            for vid in veh_ids:
                vtype = traci.vehicle.getTypeID(vid)
                wait_t = traci.vehicle.getWaitingTime(vid)
                
                target_edge_for_v = None
                try:
                    route = traci.vehicle.getRoute(vid)
                    route_idx = traci.vehicle.getRouteIndex(vid)
                    if route_idx + 1 < len(route):
                        target_edge_for_v = route[route_idx + 1]
                except:
                    pass
                
                is_blocked = False
                if target_edge_for_v:
                    try:
                        if traci.edge.getLastStepOccupancy(target_edge_for_v) > 0.82:
                            is_blocked = True
                    except: pass
                    
                if not is_blocked:
                    if vtype == "ambulance":
                        w_emergency += 0.4 * math.exp(min(wait_t, 15))
                        density += 0.3
                    else:
                        w_normal += wait_t
                        if vtype == "bike": density += 0.1
                        elif vtype == "car": density += 0.2
                        elif vtype in ["truck", "bus"]: density += 0.4
            
            m_offload = 0
            valid_out_edges = [out_e for out_e in self.outgoing_edges if out_e in global_scores]
            if valid_out_edges:
                m_offload = sum(global_scores[out_e] for out_e in valid_out_edges) / len(valid_out_edges)
            
            base_score = w_normal + w_emergency + (0.4 * density)
            penalized_score = max(0, base_score - (0.2 * m_offload))
            
            edge_len = self.edge_lengths[edge]
            normalized_score = penalized_score / edge_len if edge_len > 0 else 0
            
            scores[edge] = normalized_score
            global_scores[edge] = normalized_score 
            
        return scores

    def update(self, global_scores):
        if not self.controlled_edges:
            return
            
        scores = self.calculate_scores(global_scores)
        
        if self.state == "GREEN":
            # If current green edge has a score of 0 (either empty or targeted road is full)
            if scores[self.current_green_edge] == 0:
                best_edge = max(scores, key=scores.get) if scores else None
                if best_edge and scores[best_edge] > 0:
                    self.state = "YELLOW"
                    self.timer = 4
                    self.next_green_edge = best_edge
                    self.set_light(self.current_green_edge, 'y')
                else:
                    self.state = "ALL_RED"
                    for edge in self.controlled_edges:
                        self.set_light(edge, 'r')
            else:
                best_edge = max(scores, key=scores.get)
                
                if best_edge != self.current_green_edge:
                    current_score = scores[self.current_green_edge]
                    best_score = scores[best_edge]
                    
                    current_length = self.edge_lengths[self.current_green_edge]
                    threshold = 3.0 / current_length if current_length > 0 else 0.1
                    
                    should_switch = False
                    if current_score <= 0.01 and best_score > 0: # Use a small tolerance for floating point math
                        should_switch = True
                    elif best_score > (current_score + threshold):
                        should_switch = True
                        
                    if should_switch:
                        self.state = "YELLOW"
                        self.timer = 4  
                        self.next_green_edge = best_edge
                        self.set_light(self.current_green_edge, 'y')
                else:
                    self.set_light(self.current_green_edge, 'G')
                    
        elif self.state == "YELLOW":
            self.timer -= 1  
            if self.timer <= 0:
                self.state = "GREEN"
                self.current_green_edge = self.next_green_edge
                self.set_light(self.current_green_edge, 'G')
                
        elif self.state == "ALL_RED":
            # Check if any road has opened up
            best_edge = max(scores, key=scores.get) if scores else None
            if best_edge and scores[best_edge] > 0:
                self.state = "GREEN"
                self.current_green_edge = best_edge
                self.set_light(self.current_green_edge, 'G')

def run_simulation():
    # Load the network to map the logic
    net = sumolib.net.readNet('grid.net.xml')
    
    # Initialize the 9 independent workers
    tls_ids = traci.trafficlight.getIDList()
    workers =[JunctionWorker(tls, net) for tls in tls_ids]
    
    global_edge_scores = {} # Shared memory for M_offload calculations
    step = 0
    import collections
    edge_accumulated_wait = collections.defaultdict(int)
    all_edges = [e.getID() for e in net.getEdges() if not e.getID().startswith(':')]

    print("Simulation started. Workers actively monitoring traffic...")
    # Main simulation loop
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        
        # Track where vehicles are waiting the most (halting number = 1 vehicle waiting for 1 second)
        for e in all_edges:
            halting_count = traci.edge.getLastStepHaltingNumber(e)
            if halting_count > 0:
                edge_accumulated_wait[e] += halting_count
        
        # Trigger all 9 workers simultaneously
        for worker in workers:
            worker.update(global_edge_scores)
            
        step += 1

    traci.close()
    print("Simulation complete.")

    import xml.etree.ElementTree as ET
    import os

    print("\n" + "="*60)
    print(" 🚦 TRAFFIC SIMULATION BENCHMARK REPORT 🚦 ".center(60))
    print("="*60)
    
    # Parse vehicle stats from tripinfo and routes
    try:
        if os.path.exists("routes.rou.xml") and os.path.exists("tripinfo.xml"):
            # Map vehicles to paths
            vid_to_path = {}
            route_tree = ET.parse("routes.rou.xml")
            for trip in route_tree.getroot().findall('trip'):
                vid = trip.get('id')
                orig = trip.get('from')
                dest = trip.get('to')
                # Human-readable path cleanup if possible
                vid_to_path[vid] = f"{orig} -> {dest}"

            # Parse trip info
            tree = ET.parse("tripinfo.xml")
            root = tree.getroot()
            
            wait_by_type = collections.defaultdict(list)
            wait_by_path = collections.defaultdict(list)
            total_wait = 0
            count = 0
            
            for tripinfo in root.findall('tripinfo'):
                vid = tripinfo.get('id')
                vtype = tripinfo.get('vType')
                wait_time = float(tripinfo.get('waitingTime'))
                
                total_wait += wait_time
                count += 1
                wait_by_type[vtype].append(wait_time)
                
                if vid in vid_to_path:
                    wait_by_path[vid_to_path[vid]].append(wait_time)
                    
            if count > 0:
                print(f"Total Vehicles Processed: {count}")
                print(f"Overall Average Waiting Time: {total_wait/count:.2f} seconds")
                
                print("\n--- Average Waiting Time per Vehicle Type ---")
                for vt in sorted(wait_by_type.keys()):
                    avg = sum(wait_by_type[vt]) / len(wait_by_type[vt])
                    print(f"  {vt.capitalize():<12}: {avg:.2f} seconds ({len(wait_by_type[vt])} vehicles)")
                    
                print("\n--- Average Waiting Time per Path ---")
                for path in sorted(wait_by_path.keys()):
                    avg = sum(wait_by_path[path]) / len(wait_by_path[path])
                    print(f"  {path:<20}: {avg:.2f} seconds ({len(wait_by_path[path])} vehicles)")
        else:
            print("Could not find tripinfo.xml or routes.rou.xml for path stats.")
    except Exception as e:
        print(f"Error calculating stats: {e}")

    print("\n--- Top 5 Most Congested Roads (Bottlenecks) ---")
    sorted_edges = sorted(edge_accumulated_wait.items(), key=lambda x: x[1], reverse=True)
    found_congestion = False
    for edge, wait_secs in sorted_edges[:5]:
        if wait_secs > 0:
            found_congestion = True
            print(f"  {edge:<15}: {wait_secs} total vehicle-seconds of wait time")
    if not found_congestion:
        print("  No significant congestion recorded.")
        
    print("="*60 + "\n")

if __name__ == "__main__":
    import sys
    
    # Define the SUMO command to launch the visual GUI with our config
    sumo_cmd = ["sumo-gui", "-c", "sim.sumocfg", "--tripinfo-output", "tripinfo.xml"]
    
    # Start TraCI
    print("Starting TraCI and SUMO-GUI...")
    traci.start(sumo_cmd)
    
    # Run our multi-worker simulation logic
    run_simulation()