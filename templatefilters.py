from google.appengine.ext.webapp import template

def truncate(value, size):
	return value[0:size]

def truncate_dot(value, size):
	if len(value) > size and size > 3:
		return value[0:(size-3)] + '...'
	else:
		return value[0:size]

register = template.create_template_register()
register.filter(truncate)
register.filter(truncate_dot)

