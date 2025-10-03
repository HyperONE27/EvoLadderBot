"""
Implements a reader/writer for the database.

Backend services must use these classes to read and write to the database.
"""

class DatabaseReader:
    """
    Reads from the database.
    """
    def __init__(self):
        self.db = Database()

class DatabaseWriter:
    """
    Writes to the database.
    """
    def __init__(self):
        self.db = Database()