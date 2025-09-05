import numpy as np
from src import event
import paho.mqtt.client as mqtt
import time

from pycompss.api.task import task


# MQTT broker config
MQTT_BROKER_IP = "192.168.50.13"
MQTT_BROKER_PORT = 1883
MQTT_TOPIC = "alerts"

# MQTT broker connection will be handled by task nodes. 
# So it's declared here. Every worker will have it's own
# It's also closed from the worker, in its function
mqtt_client = mqtt.Client()
try:
    mqtt_client.connect(MQTT_BROKER_IP, MQTT_BROKER_PORT)
    print(f"[main.py] Successfully connected to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}")
except Exception as e:
    alerts = False
    print(f"[main.py] ERROR connecting to MQTT broker at {MQTT_BROKER_IP}:{MQTT_BROKER_PORT}: {e}")

def speed_task(t, view_transformer, ts):
    # Update tracklet latest 2 locations
    pixel_bc = t.to_bc()[0:2]
    mapPoints = view_transformer.pixel_to_map(pixel = [(pixel_bc[0], pixel_bc[1])])[0]#.astype(int)[0]
    t.location = mapPoints
    
    
    if t.prev_location is not None: 
        print(f'XXXXX prev loc: {t.prev_location}')
        print(f'XXXXX loc: {t.location}')
        distance = np.sqrt(np.sum(np.power(t.location - t.prev_location, 2)))
        t.distances = np.append(t.distances, distance)
        t.prev_location = t.location

    else: 
        online_speeds = f"#{t.track_id} NaN km/h /n"
        print(f'XXXXX first prev loc: {t.prev_location}')
        t.prev_location = t.location

    if t.prev_ts is not None:
        delta_ts = (ts - t.prev_ts)
        t.prev_ts = ts
    
   
        # Calculate speed
        print(f'XXXXX delta_ts: {delta_ts}')
        print(f'XXXXX distance: {distance}')

        speed = (distance / (delta_ts / 1000000)) * 3.6
        # t.speeds = np.append(t.speeds, speed)
        # Mantener solo las últimas 5 velocidades (append y recortar)
        if t.speeds.size >= 5:
            # Desplazar hacia la izquierda y colocar el nuevo al final
            t.speeds = np.roll(t.speeds, -1)
            t.speeds[-1] = speed
        else:
            t.speeds = np.append(t.speeds, speed)
            
        print(f'XXXXX speed: {t.speeds} for {t.track_id}')
        t.median_speed = np.median(t.speeds)
        online_speeds = f"#{t.track_id} {t.median_speed.astype(int)} km/h /n" # 
    else:
        online_speeds = f"#{t.track_id} NaN km/h /n"
        t.prev_ts = ts

        
    return t, online_speeds

def semantics_task(t, polys, ts , frameId, alerts):
    # Defining the kind or event or semantics polygon is on
    t.event = event.Event(t, polys, ts, frameId, t.track_id)
    # t.event = compss_wait_on(t.event)
    if (alerts):
        if(t.event.alertFlag):
            alertInfo= str(t.event)
            mqtt_client.publish(MQTT_TOPIC, t.event.to_json(), qos=0)
            return t, alertInfo
    return t, "No alerts"

#@task(returns=5)
def process_tracklets(t, view_transformer, timers, get_semantic, get_speed , alerts , polys, ts, frameId):
    
    # get speed of tracklets
    t_i = time.time()
    if (get_speed):
        t, online_speeds = speed_task(t, view_transformer, ts)
    else:
        online_speeds = "# Speed disabled"
    t_speed = time.time() - t_i

    # Check semantics and send alerts
    t_i = time.time()
    if (get_semantic): 
        t, alertInfo = semantics_task(t, polys, ts, frameId, ts)
    else:
        alertInfo = "Semantics disabled."
    t_semantics = time.time() - t_i

    return t, alertInfo, online_speeds, t_speed, t_semantics
    
    
    
def mqttClose():
    try:
        mqtt_client.disconnect()
        print(f"[main.py] Done closing connection with MQTT broker.\n")
    except Exception as e:
        print(f"[main.py] ERROR disconnecting from MQTT broker: {e}")
