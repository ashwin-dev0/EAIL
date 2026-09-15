import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent.parent/'tests')))
    raise SystemExit(0 if result.wasSuccessful() else 1)
