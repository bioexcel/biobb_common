name = "biobb_common"
__all__ = ["generic", "tools"]
__version__ = "5.2.0"


class BioBBGlobalProperties(dict):
    """Global properties container for all BiobbObject instances."""

    def __init__(self):
        super().__init__()

    def dict(self):
        """Create a shallow copy of the global properties."""
        return self.copy()

    def __repr__(self):
        """String representation."""
        return f"BioBBGlobalProperties({dict(self)})"


# Create a global instance
biobb_global_properties = BioBBGlobalProperties()
