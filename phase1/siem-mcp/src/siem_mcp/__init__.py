"""siem-mcp — MCP server over the Sahel Information Environment Monitor.

Exposes the dashboard's analytics (event counts, lethality, actor composition, admin-1
hotspots, spatial and bounding-box queries, ingestion status) as MCP tools, resources and a
prompt, so an agent can ask the questions an analyst asks of the map.

Two backends behind one interface: a synthetic SQLite store that ships with the code (no ACLED
data is redistributed), and a PostgreSQL/PostGIS store for the live database.
"""

__version__ = "0.1.0"
