# Message format examples

## Incoming messages

#### JellingStone/30:ae:a4:8a:2b:e0
```json
{
  "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
  "major": 12,
  "minor": 1,
  "timestamp": "2018-10-04T14:15:56Z",
  "comment": "stone_01",
  "data": [
    {
      "min": -97,
      "max": -83,
      "avg": -87,
      "remoteRssi": 0,
      "major": 12,
      "minor": 2,
      "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
      "mac": "30:ae:a4:8a:2b:e1"
    },
    {
      "min": -64,
      "max": -60,
      "avg": -62,
      "remoteRssi": 0,
      "mac": "68:64:4b:15:1d:37"
    }
  ]
}
```

#### NameUpdate
```json
{
  "mac": "30:ae:a4:8a:2b:e1",
  "name": "Testknoten",
  "color": "#ff0000"
}
```

## Outgoing messages

#### Aggregated/Stones
```json
{
  "30:ae:a4:8a:2b:e0": {
    "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
    "major": 12,
    "minor": 1,
    "comment": "stone_01",
    "last_seen": 1538655372,
    "contacts": [
      {
        "mac": "30:ae:a4:8a:2b:e1",
        "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
        "major": 12,
        "minor": 2,
        "rssi_avg": -42,
        "rssi_tx": 0
      },
      {
        "mac": "68:64:4b:15:1d:37",
        "uuid": "",
        "major": 0,
        "minor": 0,
        "rssi_avg": -87,
        "rssi_tx": 0
      }
    ]
  },
  "30:ae:a4:8a:2b:e1": {
    "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
    "major": 12,
    "minor": 2,
    "comment": "stone_02",
    "last_seen": 1538655375,
    "contacts": [
      {
        "mac": "30:ae:a4:8a:2b:e0",
        "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
        "major": 12,
        "minor": 1,
        "rssi_avg": -45,
        "rssi_tx": 0
      },
      {
        "mac": "68:64:4b:15:1d:37",
        "uuid": "",
        "major": 0,
        "minor": 0,
        "rssi_avg": -66,
        "rssi_tx": 0
      }
    ]
  }
}
```

#### Aggregated/Graph
```json
{
  "30:ae:a4:8a:2b:e0": {
    "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
    "major": 12,
    "minor": 1,
    "comment": "stone_01",
    "age": 0,
    "contacts": [
      {
        "mac": "30:ae:a4:8a:2b:e1",
        "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
        "major": 12,
        "minor": 2,
        "age": 0,
        "rssi_avg": -42,
        "rssi_tx": 0
      },
      {
        "mac": "68:64:4b:15:1d:37",
        "uuid": "",
        "major": 0,
        "minor": 0,
        "age": 16,
        "rssi_avg": -87,
        "rssi_tx": 0
      }
    ]
  },
  "30:ae:a4:8a:2b:e1": {
    "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
    "major": 12,
    "minor": 2,
    "comment": "stone_02",
    "last_seen": 5,
    "contacts": [
      {
        "mac": "30:ae:a4:8a:2b:e0",
        "uuid": "fd:b5:06:73:a4:22:4f:f1:af:af:c6:0b:27:6b:78:35",
        "major": 12,
        "minor": 1,
        "age": 5,
        "rssi_avg": -45,
        "rssi_tx": 0
      },
      {
        "mac": "68:64:4b:15:1d:37",
        "uuid": "",
        "major": 0,
        "minor": 0,
        "age": 21,
        "rssi_avg": -66,
        "rssi_tx": 0
      }
    ]
  }
}
```

#### Aggregated/Names
```json
{
  "30:ae:a4:8a:2b:e0": {
    "name": "L. Mueller",
    "color": "#0000ff"
  },
  "30:ae:a4:8a:2b:e1": {
    "name": "Testknoten",
    "color": "#ff0000"
  }
}
```
