class PolySemantic:
        def __init__(self, polyGeo, idVGGIA, polyType):
            print('Initiating with poly semantics')
            self.poly = polyGeo
            self.id = idVGGIA
            self.type = polyType


        def __str__(self):
            return (
                f"poly:    {self.poly}\n"
                f"id:     {self.id}\n"
                f"type:     {self.type}\n"
            )
