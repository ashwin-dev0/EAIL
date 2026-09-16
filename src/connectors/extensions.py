"""Administrator-owned extension point for additional source databases/APIs.
Register classes implementing Adapter.fetch(dataset, period), not import paths
from user requests. Source grants, projection, snapshots and limits still apply.
Restart services after installing/reviewing a source adapter.
"""
ADAPTER_FACTORIES = {}
# Example after implementing/reviewing a driver:
# from src.connectors.my_database import MyDatabaseAdapter
# ADAPTER_FACTORIES['my_database'] = MyDatabaseAdapter
