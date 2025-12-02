"""Test script to start Sync Sampling on node 10603"""
import mscl
import time

# Connect to BaseStation
connection = mscl.Connection.TcpIp("192.168.8.101", 5000)
base_station = mscl.BaseStation(connection)

print("Connected to BaseStation")

# Create node
node = mscl.WirelessNode(10603, base_station)

# Create Sync Sampling Network
sync_network = mscl.SyncSamplingNetwork(base_station)

print("Attempting to add node to sync network...")

# Try to add node - may fail if needs EEPROM read
try:
    sync_network.addNode(node)
    print("  Node added successfully!")
except Exception as e:
    print(f"  Failed to add node: {e}")
    exit(1)

# Start the network
print("\nApplying network configuration...")
try:
    sync_network.applyConfiguration()
    print("  ✓ Configuration applied!")
except Exception as e:
    print(f"  Error applying config: {e}")
    exit(1)

print("\nStarting sync sampling network...")
try:
    sync_network.startSampling()
    print("  ✓ Sync sampling started!")
    print("\nListening for data (5 seconds)...")
    
    for i in range(5):
        sweeps = base_station.getData(1000)
        print(f"  Iteration {i+1}: Got {len(sweeps)} sweeps")
        for sweep in sweeps:
            if sweep.nodeAddress() == 10603:
                print(f"    → Sweep from 10603: {len(sweep.data())} data points")
        time.sleep(1)
    
    # Stop sampling
    print("\nStopping sync sampling...")
    sync_network.stopSampling()
    print("  ✓ Stopped")
    
except Exception as e:
    print(f"  Error: {e}")

print("\nTest complete!")
