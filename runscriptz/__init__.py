from .runscriptz import RunScriptzExtension

# And add the extension to Krita's list of extensions:
app = Krita.instance()
# Instantiate your class:
extension = RunScriptzExtension(parent = app)
app.addExtension(extension)
