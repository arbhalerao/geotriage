import os

REGISTRY = os.getenv("REGISTRY", "localhost")

BUILTIN_MODELS = [
    f"{REGISTRY}/geotriage/ndwi-water:0.1",
    f"{REGISTRY}/geotriage/lst:0.1",
]

BUILTIN_PROVIDERS = [
    f"{REGISTRY}/geotriage/earth-search:0.1",
    f"{REGISTRY}/geotriage/planetary-computer:0.1",
]
