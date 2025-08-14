# 🏗️ SmartCity COMPSs - Visual System Architecture
## For Presentation & Technical Overview

---

## 📐 System Architecture Overview

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                           SMART CITY COMPSS PLATFORM                          │
│                        Real-Time Object Tracking & Analytics                  │
└───────────────────────────────────────────────────────────────────────────────┘
                                        │
                            ┌───────────┴───────────┐
                            │   SYSTEM WORKFLOW     │
                            └───────────┬───────────┘
                                        │
         ┌──────────────┬───────────────┼───────────────┬──────────────┐
         │              │               │               │              │
         ▼              ▼               ▼               ▼              ▼
    [1] INPUT      [2] RECEIVE    [3] TRACKING    [4] ANALYTICS   [5] OUTPUT
   Edge Cameras   Communication   Multi-Object     Parallel      Streaming
                   & Protocol      Detection      Processing     & Storage
```

---

## 🎥 Step 1: Edge Camera Input Layer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              EDGE CAMERAS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  📷 CAMERA 1        📷 CAMERA 2        📷 CAMERA 3        📷 CAMERA N      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │   YOLO/AI   │    │   YOLO/AI   │    │   YOLO/AI   │    │   YOLO/AI   │   │
│  │ DETECTION   │    │ DETECTION   │    │ DETECTION   │    │ DETECTION   │   │
│  │             │    │             │    │             │    │             │   │
│  │ • Vehicles  │    │ • Pedestrian│    │ • Bicycles  │    │ • Objects   │   │
│  │ • People    │    │ • Traffic   │    │ • Vehicles  │    │ • Custom    │   │
│  │ • Objects   │    │ • Objects   │    │ • Signs     │    │ • Classes   │   │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘   │
│         │                   │                   │                   │       │
│         ▼                   ▼                   ▼                   ▼       │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐   │
│  │  BOUNDING   │    │  BOUNDING   │    │  BOUNDING   │    │  BOUNDING   │   │
│  │   BOXES     │    │   BOXES     │    │   BOXES     │    │   BOXES     │   │
│  │             │    │             │    │             │    │             │   │
│  │ [x,y,w,h]   │    │ [x,y,w,h]   │    │ [x,y,w,h]   │    │ [x,y,w,h]   │   │
│  │ + class     │    │ + class     │    │ + class     │    │ + class     │   │
│  │ + conf      │    │ + conf      │    │ + conf      │    │ + conf      │   │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                               📡 UDP/ZMQ TRANSMISSION
```

**What happens here:**
- Edge cameras capture live video feeds
- AI models (YOLO) detect objects in real-time
- Generate bounding boxes with coordinates, class, and confidence
- Send detection data via UDP/ZMQ protocols

---

## 📡 Step 2: Communication & Protocol Layer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         COMMUNICATION PROTOCOLS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │   UDP HANDLER   │  │   ZMQ HANDLER   │  │  MQTT HANDLER   │             │
│  │                 │  │                 │  │                 │             │
│  │ • Low Latency   │  │ • Reliable      │  │ • Alerts        │             │
│  │ • High Speed    │  │ • Multi-Topic   │  │ • Notifications │             │
│  │ • Real-time     │  │ • Scalable      │  │ • Events        │             │
│  │                 │  │                 │  │                 │             │
│  │ 🚀 <100ms      │  │ 📦 Guaranteed   │  │ 🔔 Instant     │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│           │                     │                     │                     │
│           └─────────────────────┼─────────────────────┘                     │
│                                 │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DATA PREPROCESSING                             │   │
│  │                                                                     │   │
│  │  • Frame Synchronization     • Data Validation                     │   │
│  │  • Format Standardization    • Error Handling                      │   │
│  │  • Camera Calibration        • Duplicate Removal                   │   │
│  │  • Coordinate Mapping        • Quality Control                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                                🎯 UNIFIED DATA STREAM
```

**What happens here:**
- Multiple communication protocols handle different data types
- Frame synchronization ensures temporal consistency
- Data validation and preprocessing before tracking
- Unified stream preparation for tracking algorithms

---

## 🎯 Step 3: Multi-Object Tracking Engine

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BYTETRACK TRACKING ENGINE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        DETECTION ASSOCIATION                        │   │
│  │                                                                     │   │
│  │  New Frame    ┌─────────────┐    Hungarian     ┌─────────────┐      │   │
│  │  Detections ──│   KALMAN    │──▶ Algorithm   ──│   TRACK     │      │   │
│  │      │        │   FILTER    │    Matching      │   UPDATE    │      │   │
│  │      │        │             │                  │             │      │   │
│  │      ▼        │ • Predict   │                  │ • New IDs   │      │   │
│  │  ┌─────────┐  │ • Update    │                  │ • Update    │      │   │
│  │  │ HIGH    │  │ • Velocity  │                  │ • Lost      │      │   │
│  │  │ CONF    │  └─────────────┘                  └─────────────┘      │   │
│  │  │ DETECT  │         │                               │              │   │
│  │  └─────────┘         ▼                               ▼              │   │
│  │      │        ┌─────────────┐                 ┌─────────────┐      │   │
│  │      │        │   TRACK     │                 │   ACTIVE    │      │   │
│  │      │        │ PREDICTION  │                 │   TRACKS    │      │   │
│  │      │        └─────────────┘                 └─────────────┘      │   │
│  │      │                                                             │   │
│  │      ▼                                                             │   │
│  │  ┌─────────┐       ┌─────────────────────────────────────────┐    │   │
│  │  │ LOW     │       │            TRACK LIFECYCLE             │    │   │
│  │  │ CONF    │       │                                         │    │   │
│  │  │ DETECT  │       │  NEW → ACTIVE → LOST → REMOVED         │    │   │
│  │  └─────────┘       │   │      │       │        │            │    │   │
│  │      │              │   │   30 FPS    │    Timeout          │    │   │
│  │      │              │   │  Tracking   │   Recovery          │    │   │
│  │      └──────────────▶   │             │                     │    │   │
│  │                     │   ▼             ▼                     │    │   │
│  │                     │ ID: 001      ID: 001                  │    │   │
│  │                     │ Pos: (x,y)   Missing                  │    │   │
│  │                     │ Speed: v     Frames: 5                │    │   │
│  │                     └─────────────────────────────────────────┘    │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          OUTPUT GENERATION                          │   │
│  │                                                                     │   │
│  │  🎯 Track ID: 001     📍 Position: (120, 340)                     │   │
│  │  🚗 Class: Vehicle    📏 Dimensions: 80x40                         │   │
│  │  ⚡ Speed: 45 km/h    🕒 Timestamp: 12:34:56.789                   │   │
│  │  📐 UTM Coords        🎪 Trajectory: [(x1,y1), (x2,y2)...]         │   │
│  │  ✅ Status: Active    🎨 Bounding Box: [x, y, w, h]                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                                  📊 TRACKED OBJECTS
```

**What happens here:**
- ByteTrack algorithm processes all detections
- Kalman filters predict object movement
- Hungarian algorithm matches detections to existing tracks
- Maintains object IDs through occlusions and miss-detections
- Generates rich tracking data with speed, trajectory, and status

---

## ⚡ Step 4: COMPSs Parallel Analytics

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPSS PARALLEL PROCESSING                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │    CLUSTER      │  │    CLUSTER      │  │    CLUSTER      │             │
│  │    NODE 1       │  │    NODE 2       │  │    NODE N       │             │
│  │                 │  │                 │  │                 │             │
│  │ ┌─────────────┐ │  │ ┌─────────────┐ │  │ ┌─────────────┐ │             │
│  │ │   SPEED     │ │  │ │  SEMANTIC   │ │  │ │   EVENT     │ │             │
│  │ │ CALCULATION │ │  │ │  ANALYSIS   │ │  │ │ DETECTION   │ │             │
│  │ │             │ │  │ │             │ │  │ │             │ │             │
│  │ │ @task       │ │  │ │ @task       │ │  │ │ @task       │ │             │
│  │ │ def calc_   │ │  │ │ def check_  │ │  │ │ def detect_ │ │             │
│  │ │ speed()     │ │  │ │ roi()       │ │  │ │ violations()│ │             │
│  │ └─────────────┘ │  │ └─────────────┘ │  │ └─────────────┘ │             │
│  │                 │  │                 │  │                 │             │
│  │ • UTM Transform │  │ • ROI Checking  │  │ • Rule Violations│             │
│  │ • Velocity Calc │  │ • Polygon Areas │  │ • Anomaly Detect│             │
│  │ • Distance Meas │  │ • Restricted    │  │ • Alert Trigger │             │
│  │ • Direction     │  │   Zones         │  │ • Event Logger  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│           │                     │                     │                     │
│           └─────────────────────┼─────────────────────┘                     │
│                                 │                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      TASK ORCHESTRATION                             │   │
│  │                                                                     │   │
│  │        COMPSs Runtime automatically:                                │   │
│  │        • Distributes tasks across available nodes                  │   │
│  │        • Manages data dependencies                                  │   │
│  │        • Handles fault tolerance                                    │   │
│  │        • Optimizes resource utilization                            │   │
│  │        • Provides transparent parallelization                      │   │
│  │                                                                     │   │
│  │  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐          │   │
│  │  │ Task 1  │    │ Task 2  │    │ Task 3  │    │ Task N  │          │   │
│  │  │ Object  │    │ Object  │    │ Object  │    │ Object  │          │   │
│  │  │ ID: 001 │───▶│ ID: 002 │───▶│ ID: 003 │───▶│ ID: N   │          │   │
│  │  │ Speed   │    │ ROI     │    │ Event   │    │ Alert   │          │   │
│  │  └─────────┘    └─────────┘    └─────────┘    └─────────┘          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                                  🧠 ENRICHED DATA
```

**What happens here:**
- COMPSs automatically distributes analytics tasks across cluster nodes
- Parallel processing of speed calculation, semantic analysis, and event detection
- Task orchestration handles dependencies and resource optimization
- Rich analytics data generated for each tracked object

---

## 📤 Step 5: Output & Streaming Layer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OUTPUT & STREAMING                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │     KAFKA       │  │      CSV        │  │     VIDEO       │             │
│  │   STREAMING     │  │    EXPORT       │  │    OVERLAY      │             │
│  │                 │  │                 │  │                 │             │
│  │ • Real-time     │  │ • Batch Files   │  │ • Annotated     │             │
│  │ • Avro Schema   │  │ • Historical    │  │ • Bounding Box  │             │
│  │ • Partitioned   │  │ • Analytics     │  │ • Track IDs     │             │
│  │ • Scalable      │  │ • Reports       │  │ • Speed Labels  │             │
│  │                 │  │                 │  │                 │             │
│  │ 🌊 Stream       │  │ 📊 Batch       │  │ 🎥 Visual      │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│           │                     │                     │                     │
│           │                     │                     │                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐             │
│  │     MQTT        │  │   DASHBOARD     │  │   DATABASE      │             │
│  │    ALERTS       │  │   ANALYTICS     │  │    STORAGE      │             │
│  │                 │  │                 │  │                 │             │
│  │ • Violations    │  │ • Real-time     │  │ • Time Series   │             │
│  │ • Anomalies     │  │ • Metrics       │  │ • Historical    │             │
│  │ • Emergency     │  │ • Visualizations│  │ • Queryable     │             │
│  │ • Notifications │  │ • KPIs          │  │ • Indexed       │             │
│  │                 │  │                 │  │                 │             │
│  │ 🚨 Instant     │  │ 📈 Live        │  │ 💾 Persistent  │             │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘             │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                          DATA FLOW                                  │   │
│  │                                                                     │   │
│  │  📊 Enriched Data ──┬──▶ Kafka Topic: "city-tracking"              │   │
│  │                     ├──▶ CSV Files: "/data/tracking_YYYYMMDD.csv"   │   │
│  │                     ├──▶ Video Stream: Real-time annotation         │   │
│  │                     ├──▶ MQTT Alerts: "alerts/violations"           │   │
│  │                     ├──▶ Dashboard: Live metrics                    │   │
│  │                     └──▶ Database: Time-series storage              │   │
│  │                                                                     │   │
│  │  🔄 Frame-based Flush: Every 30 frames or 1 second                 │   │
│  │  📏 Schema Registry: Automatic schema evolution                     │   │
│  │  🔐 Security: SASL/SSL authentication                               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
                            📱 SMART CITY APPLICATIONS
```

**What happens here:**
- Multiple output formats for different use cases
- Real-time Kafka streaming for live applications
- Batch CSV exports for historical analysis
- Video overlays for visual monitoring
- MQTT alerts for immediate notifications
- Dashboard integration for live metrics

---

## 🔄 Complete Data Flow Summary

```
📷 CAMERAS → 📡 PROTOCOLS → 🎯 TRACKING → ⚡ ANALYTICS → 📤 STREAMING
     │            │            │            │             │
  [Objects]   [BBox Data]   [Tracks]   [Enriched]    [Multiple]
  Detection   UDP/ZMQ       ByteTrack   COMPSs        Outputs
   YOLO/AI    Real-time     Algorithm   Parallel      Kafka/CSV
  Recognition Transport     Multi-Obj   Processing    /Video/MQTT
```

### Performance Metrics:
- **End-to-end Latency**: < 200ms (camera to output)
- **Processing Rate**: 20-30 FPS per camera
- **Scalability**: Linear scaling with cluster size
- **Accuracy**: 95%+ tracking precision
- **Throughput**: 1000+ objects/second

---

## 💡 Key Innovation Points

### 1. **Distributed Architecture**
- Automatic parallelization with COMPSs
- Fault-tolerant cluster computing
- Dynamic resource allocation

### 2. **Real-Time Performance**
- Ultra-low latency processing
- Frame-synchronized operations
- Optimized data pipelines

### 3. **Enterprise Integration**
- Multiple output formats
- Schema evolution support
- Security and authentication

### 4. **Smart City Ready**
- Traffic management analytics
- Public safety monitoring
- Urban planning insights

---

*This architecture enables cities to transform raw video feeds into actionable intelligence through distributed real-time processing and enterprise-grade data streaming.*
