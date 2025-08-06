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

def speed_task(t, view_transformer, FPS):
    # Update tracklet latest 2 locations
    mapPoints = view_transformer.transform_points(points = t.to_bc()[0:2])#.astype(int)
    if t.location is not None: 
        t.prev_location = t.location
        t.location = mapPoints
        # Calculate speed
        distance = np.square(np.sum((np.power(abs(t.location - t.prev_location),2))))
        time = 1 / FPS
        speed = (distance / time) * 3.6
        # t.speeds = np.append(t.speeds, speed)
        
                # Mantener solo las últimas 5 velocidades (append y recortar)
        if t.speeds.size >= 5:
            # Desplazar hacia la izquierda y colocar el nuevo al final
            t.speeds = np.roll(t.speeds, -1)
            t.speeds[-1] = speed
        else:
            t.speeds = np.append(t.speeds, speed)
        
        t.median_speed = np.median(t.speeds)
        
        online_speeds = f"#{t.track_id} {t.median_speed.astype(int)} km/h /n" # 
    else:
        t.location = mapPoints
        online_speeds = f"#{t.track_id} --No map points-- km/h /n"
        
    return t, online_speeds

def semantics_task(t, polys, ts , frameId, alerts):
    t.event = event.Event(t, polys, ts, frameId, t.track_id)
    # t.event = compss_wait_on(t.event)
    if (alerts):
        if(t.event.alertFlag):
            alertInfo= str(t.event)
            mqtt_client.publish(MQTT_TOPIC, t.event.to_json(), qos=0)
            return t, alertInfo
    return t, "No alerts"

@task(returns=5)
def process_tracklets(t, view_transformer, timers, semantics, get_speed , alerts ,
                      FPS, polys, ts, frameId):
    
    # get speed of tracklets
    t_i = time.time()
    if (get_speed):
        t, online_speeds = speed_task(t, view_transformer, FPS)
    else:
        online_speeds = "# Speed disabled"
    t_speed = time.time() - t_i

    # Check semantics and send alerts
    t_i = time.time()
    if (semantics): 
        t, alertInfo = semantics_task(t, polys, ts, frameId, alerts)
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
