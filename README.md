# AI Maze Solver - Location Finder

## Demo Video

Start here first to see the project in action: [Video of project working.mp4](Video%20of%20project%20working.mp4)

This project is a desktop Python app that combines a maze solver with real-world route finding.

It provides two main modes:

- Maze solving on a 20x20 grid using BFS and DFS
- Real city-to-city route lookup using OpenStreetMap, Nominatim, OSRM, and an optional Folium interactive map

## Features

- Draw walls, erase cells, and place start/end points with the mouse
- Solve the maze with BFS for the shortest path
- Solve the maze with DFS for a deeper search path
- Generate a random maze
- Clear the whole grid or only the solved path
- Search real cities and compare road distance with straight-line distance
- Create and open an interactive HTML route map

## Requirements

- Python 3.10 or later
- `numpy`
- `requests`
- `folium` for the interactive map feature

The maze solver GUI uses `tkinter`, which is included with most standard Python installations on Windows.

## Install

From the project folder, install the Python packages:

```bash
pip install numpy requests folium
```

If `folium` is missing, the app can try to install it automatically when you open the interactive map.

## Run

Start the application with:

```bash
python projectAI.py
```

## How to Use

### Maze Solver

1. Choose a drawing mode on the left panel.
2. Click on the grid to draw walls and place the start/end cells.
3. Pick `BFS` or `DFS`.
4. Click `SOLVE`.

### Real Map Routing

1. Enter a start city and an end city on the right panel.
2. Click `Find Route + Map` to get the road route and distance information.
3. Click `Open Interactive Map` to generate and open `route_map.html` in your browser.

## Output Files

- `route_map.html` is generated when the interactive map is created.

## Notes

- BFS is the shortest-path search.
- DFS may find a valid path, but it is not guaranteed to be the shortest.
- Real map routing depends on internet access because it calls public OpenStreetMap and OSRM services.

## Project Files

- `projectAI.py` - main application
- `route_map.html` - generated interactive map output
