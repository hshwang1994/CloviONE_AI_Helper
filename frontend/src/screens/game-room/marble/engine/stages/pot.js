/* 경주 판 「탐욕의 항아리」(원본 이름 「Pot of greed」) — lazygyu/roulette 의 src/data/maps.ts 에서 옮긴 자료 (MIT, ATTRIBUTION.md).
 * 원본 커밋 47ff61e6e3ea612638b30442753e14e037ab371e 의 값을 그대로 둔다 — 좌표 · 반폭 · 회전(라디안) · 밀도 · 반발 · 각속도 · life. 그리기 색은 여기 없다(제품 팔레트가 정한다).
 * `scripts/marble_import_maps.py` 가 만든 파일이라 손으로 고치지 않는다. */

export const POT = {
 "title": "Pot of greed",
 "goalY": 91,
 "zoomY": 92.5,
 "entities": [
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      17,
      -300
     ],
     [
      9,
      -300
     ],
     [
      9,
      8.5
     ],
     [
      2,
      15
     ],
     [
      6,
      61.5
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      7,
      67.2
     ],
     [
      9,
      85.2
     ],
     [
      8,
      84.9
     ],
     [
      6,
      84.6
     ],
     [
      5,
      78.6
     ],
     [
      4,
      66.6
     ],
     [
      7,
      67.2
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      17,
      -300
     ],
     [
      17,
      8.5
     ],
     [
      24,
      15
     ],
     [
      20,
      61.5
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      19,
      67.2
     ],
     [
      17,
      85.2
     ],
     [
      18,
      84.9
     ],
     [
      20,
      84.6
     ],
     [
      21,
      78.6
     ],
     [
      22,
      66.6
     ],
     [
      19,
      67.2
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      11,
      77.4
     ],
     [
      12,
      78.6
     ],
     [
      12,
      91.8
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      15,
      77.4
     ],
     [
      14,
      78.6
     ],
     [
      14,
      91.8
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      12,
      85.8
     ],
     [
      11,
      86.4
     ],
     [
      9,
      87
     ],
     [
      8,
      87
     ],
     [
      6,
      86.4
     ],
     [
      5,
      85.8
     ],
     [
      4,
      84.6
     ],
     [
      3,
      78.6
     ],
     [
      2,
      66.6
     ],
     [
      3,
      63.6
     ],
     [
      4,
      62.4
     ],
     [
      5,
      61.8
     ],
     [
      6,
      61.5
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 0,
    "y": 0
   },
   "shape": {
    "type": "polyline",
    "rotation": 0,
    "points": [
     [
      14,
      85.8
     ],
     [
      15,
      86.4
     ],
     [
      17,
      87
     ],
     [
      18,
      87
     ],
     [
      20,
      86.4
     ],
     [
      21,
      85.8
     ],
     [
      22,
      84.6
     ],
     [
      23,
      78.6
     ],
     [
      24,
      66.6
     ],
     [
      23,
      63.6
     ],
     [
      22,
      62.4
     ],
     [
      21,
      61.8
     ],
     [
      20,
      61.5
     ]
    ]
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 13,
    "y": 20
   },
   "shape": {
    "type": "box",
    "width": 3,
    "height": 3,
    "rotation": 0.7853981633974483
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 13,
    "y": 55
   },
   "shape": {
    "type": "box",
    "width": 3,
    "height": 3,
    "rotation": 0.7853981633974483
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 8,
    "y": 37
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 2,
    "rotation": 0.7853981633974483
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "static",
   "position": {
    "x": 18,
    "y": 37
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 2,
    "rotation": 0.7853981633974483
   },
   "props": {
    "density": 1,
    "angularVelocity": 0,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 11,
    "y": 12
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -3,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 15,
    "y": 12
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 3,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 8,
    "y": 87
   },
   "shape": {
    "type": "box",
    "width": 1,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 6,
    "y": 86.4
   },
   "shape": {
    "type": "box",
    "width": 1.5,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 4,
    "y": 84.6
   },
   "shape": {
    "type": "box",
    "width": 1.5,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 3.5,
    "y": 81.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 3,
    "y": 78.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 2.75,
    "y": 75.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 2.5,
    "y": 72.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 2.25,
    "y": 69.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 2,
    "y": 66.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": -10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 18,
    "y": 87
   },
   "shape": {
    "type": "box",
    "width": 1,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 20,
    "y": 86.4
   },
   "shape": {
    "type": "box",
    "width": 1.5,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 22,
    "y": 84.6
   },
   "shape": {
    "type": "box",
    "width": 1.5,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 22.5,
    "y": 81.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 23,
    "y": 78.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 23.25,
    "y": 75.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 23.5,
    "y": 72.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 23.75,
    "y": 69.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  },
  {
   "type": "kinematic",
   "position": {
    "x": 24,
    "y": 66.6
   },
   "shape": {
    "type": "box",
    "width": 2,
    "height": 0.1,
    "rotation": 0
   },
   "props": {
    "density": 1,
    "angularVelocity": 10,
    "restitution": 0
   }
  }
 ]
};

export default POT;
