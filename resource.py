# It can have all  the extern interfaces
# Lets design this resources as dependency injection container

class Resource:
    def __init__(self):
        self._resources = {}

    def register(self, name, resource):
        self._resources[name] = resource

    def get(self, name):
        return self._resources.get(name)

    def __getitem__(self, name):
        return self.get(name)

    def __setitem__(self, name, resource):
        self.register(name, resource)