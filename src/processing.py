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
    
    if t.prev_location is not None and t.prev_ts is not None: # only tracklets more than one location
        distance = np.sqrt(np.sum(np.power(t.location - t.prev_location, 2)))
        delta_ts = (ts - t.prev_ts)
        t.prev_ts = ts
        t.prev_location = t.location

        total_distance =  t.distanceAccum + distance
        total_time = delta_ts + t.timeAccum

        # If accumulated distance is > 1 meter, get speed and reset accumulators
        if (total_distance)  > 1.5:
            # Speed calculated adding to distance and time delta the previous accumulated data
            speed = (total_distance / ((total_time) / 1000000)) * 3.6
            t.distances = np.append(t.distances, total_distance)

            t.distanceAccum = 0
            t.timeAccum = 0

            if (t.speeds.size < 5):
                t.speeds = np.append(t.speeds, speed)
            else:
                t.speeds[:-1] = t.speeds[1:]
                t.speeds[-1] = speed

        else: # distance below 1 meter
            # accumulate distance and time until > 1 meter
            t.distanceAccum += distance
            t.timeAccum += delta_ts

            # Adding nan to tracker arrays
            t.distances = np.append(t.distances, np.nan)
            if (t.speeds.size < 5):
                t.speeds = np.append(t.speeds, np.nan)
            else:
                t.speeds[:-1] = t.speeds[1:]
                t.speeds[-1] = np.nan

        # Get median  of last 5 speeds. If nan is majority return nan
        if np.isnan(t.speeds).sum() == 4:
            t.median_speed = np.nan
        elif np.isnan(t.speeds).sum() == 5:
            t.median_speed = 0
        else:
            t.median_speed = np.nanmedian(t.speeds)
        online_speeds = f"#{t.track_id}  {t.median_speed:.1f} km/h /n" # 
            # online_speeds = f"#{t.track_id} NaN km/h /n"

    else: 
        # Preparing tracklet for next iteration
        t.prev_ts = ts
        t.prev_location = t.location
        t.distances = np.append(t.distances, np.nan)
        t.speeds = np.append(t.speeds, np.nan)
        online_speeds = f"#{t.track_id} NaN km/h /n"
        
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