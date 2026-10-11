"""
Investment Homelab - Modular Scripts Package
Organized into broker subpackages:
- scripts.krungsri
- scripts.liberator
- scripts.click2win
- scripts.shared
"""
import sys
import importlib
import importlib.abc
import importlib.util

_SUBPACKAGES = ["krungsri", "liberator", "click2win", "shared"]

class _ScriptsLegacyFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("scripts."):
            return None
        parts = fullname.split(".")
        if len(parts) != 2:
            return None
        script_name = parts[1]
        if script_name in _SUBPACKAGES or script_name.startswith("__"):
            return None
        
        # Check subpackages
        for subpkg in _SUBPACKAGES:
            target_mod = f"scripts.{subpkg}.{script_name}"
            try:
                spec = importlib.util.find_spec(target_mod)
                if spec is not None:
                    return spec
            except (ModuleNotFoundError, ValueError):
                continue
        return None

sys.meta_path.insert(0, _ScriptsLegacyFinder())

def __getattr__(name: str):
    for subpkg in _SUBPACKAGES:
        mod_name = f"scripts.{subpkg}.{name}"
        try:
            mod = importlib.import_module(mod_name)
            globals()[name] = mod
            return mod
        except (ModuleNotFoundError, ImportError):
            continue
    raise AttributeError(f"module 'scripts' has no attribute '{name}'")
