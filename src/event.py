from shapely import geometry
import json

class Event(object):

    ts = None
    category = None
    severity = None # informational, low, medium, high
    polyType = 'None'
    alertFlag = False
    frameId = 0   
    trackletId = 0

    def __init__(self, t, polys, timestamp, frameId, tId):
        self.ts = timestamp
        self.frameId = frameId
        self.getPolType(t, polys)
        self.eventType(t)
        self.trackletId = tId
                
    # This function sets the type of polygon the tracklet is in
    def getPolType(self, t, polys):
        for j, pol in enumerate(polys):
            inOut = pol.poly.contains(geometry.Point(t.tlwh[0] + t.tlwh[2]/2, t.tlwh[1] + t.tlwh[3]))
            if(inOut):
                print('Dentro de poligono')
                self.polyType = pol.type

    def eventType(self, t):
        print('Q')
        if(t.cl == 0): # If car
            pass
        elif(t.cl == 1): # If pedestrian
            if(self.polyType == 'road'):
                self.category = 'Pedestrian on road'
                self.severity = 'low'
                self.alertFlag = True

    def __str__(self):
        return (
            f"Timestamp:    {self.ts}\n"
            f"Category:     {self.category}\n"
            f"Severity:     {self.severity}\n"
            f"Poly Type:    {self.polyType}\n"
            f"Alert Flag:   {self.alertFlag}\n"
            f"Frame ID:     {self.frameId}\n"
            f"Tracklet ID:  {self.trackletId}"
        )


    def to_dict(self):
        return {
            "timestamp": self.ts,
            "category": self.category,
            "severity": self.severity,
            "poly_type": self.polyType,
            "alert_flag": self.alertFlag,
            "frame_id": self.frameId,
            "tracklet_id": self.trackletId
        }

    def to_json(self):
        return json.dumps(self.to_dict())

    
    def saveAlert(self):
        return f'{self.frameId} {self.trackletId} {self.ts} {self.polyType} {self.category} {self.severity}'
