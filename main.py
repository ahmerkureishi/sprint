import os
import cgi
import datetime
import logging

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext import db
import wsgiref.handlers

logging.getLogger().setLevel(logging.DEBUG)


class MainPage(webapp.RequestHandler):
	def get(self):
		'''Show the dashboard page.'''
		# Make sure we have an AppUser session object otherwise send to the user profile to make one
		user = users.get_current_user()
		app_user_query = db.GqlQuery("SELECT * FROM AppUser WHERE user = :1", user)
		app_user = app_user_query.get()
		if not app_user_query.get():
			self.redirect('/user')
		
		# Get all projects and backlogs for the right nav area
		projects = Project.all().order('title')
		backlogs = Backlog.all().order('title')
		user_list = [user for user in AppUser.all()]
		url = users.create_logout_url(self.request.uri)
		
		# Get all the user's items and the associated sprints and projects
		user_projects = [project for project in projects]
		for project in user_projects:
			sprint_query = Sprint.gql("WHERE project = :1 ORDER BY title", project)
			project.sprints = [sprint for sprint in sprint_query]
			for sprint in project.sprints:
				item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND owner = :2 ORDER BY title", sprint, app_user)
				sprint.items = [item for item in item_query]
			for sprint in project.sprints:
				if not sprint.items:
					project.sprints.remove(sprint)
		for project in user_projects:
			if not project.sprints:
				user_projects.remove(project)
		
		template_file_name = 'mainpage.html'
		template_values = {'projects': projects, 'user_projects': user_projects, 'backlogs': backlogs, 'users': user_list, 'url': url}

		path = os.path.join(os.path.dirname(__file__), template_file_name)
		self.response.out.write(template.render(path, template_values))


class UserPage(webapp.RequestHandler):
	def get(self):
		'''Show the user profile page.'''
		# Make sure the user has a profile object
		user = users.get_current_user()
		app_user_query = db.GqlQuery("SELECT * FROM AppUser WHERE user = :1", user)
		if not app_user_query.get():
			app_user = AppUser()
			app_user.user = user
			app_user.put()
			app_user.alert_message = "Please update your preferences."
		else:
			app_user = app_user_query.get()
		
		# Save a couple other items for the template
		alert = app_user.alert_message
		app_user.alert_message = None
		app_user.put()
		app_user.email = user.email()
		app_user.nickname = user.nickname()
		
		template_file_name = 'userpage.html'
		template_values = {'app_user': app_user, 'alert': alert}

		path = os.path.join(os.path.dirname(__file__), template_file_name)
		self.response.out.write(template.render(path, template_values))

	def post(self):
		'''Update the AppUser profile.'''
		id = self.request.get('id')
		app_user = AppUser.get(id)

		app_user.first_name = self.request.get('first_name')
		app_user.last_name = self.request.get('last_name')
		app_user.alert_message = "You have successfully updated your account."

		app_user.put()

		self.redirect('/user')


class ProjectPage(webapp.RequestHandler):
	def get(self):
		id = self.request.get('id')
		project = Project.get(id)
		sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
		project.sprints = [sprint for sprint in sprint_query]
		for sprint in project.sprints:
			item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 ORDER BY title", sprint)
			sprint.items = [item for item in item_query]
		
		user_list = [user for user in AppUser.all()]
		
		template_file_name = 'projectpage.html'
		template_values = {'project': project, 'users': user_list}

		path = os.path.join(os.path.dirname(__file__), template_file_name)
		self.response.out.write(template.render(path, template_values))


class CreateProject(webapp.RequestHandler):
	def post(self):
		project = Project()
		project.title = self.request.get('title')
		
		project.put()
		
		self.redirect('/')


class CreateSprint(webapp.RequestHandler):
	def post(self):
		sprint = Sprint()
		sprint.title = self.request.get('title')
		if self.request.get('project_id'):
			sprint.project = Project.get(self.request.get('project_id'))
		if self.request.get('start_date'):
			start = self.request.get('start_date').split('/')
			year = int(start[2])
			month = int(start[0])
			day = int(start[1])
			sprint.start_date = datetime.date(year, month, day)
		if self.request.get('end_date'):
			end = self.request.get('end_date').split('/')
			year = int(end[2])
			month = int(end[0])
			day = int(end[1])
			sprint.end_date = datetime.date(year, month, day)
		
		sprint.put()
		
		self.redirect(self.request.get('path'))


class BacklogPage(webapp.RequestHandler):
	def get(self):
		id = self.request.get('id')
		backlog = Backlog.get(id)
		items = db.GqlQuery("SELECT * FROM Item WHERE backlog = :1 ORDER BY title", backlog)

		user_list = [user for user in AppUser.all()]

		template_file_name = 'backlogpage.html'
		template_values = {'backlog': backlog, 'items': items, 'users': user_list}
		
		path = os.path.join(os.path.dirname(__file__), template_file_name)
		self.response.out.write(template.render(path, template_values))


class CreateBacklog(webapp.RequestHandler):
	def post(self):
		backlog = Backlog()
		backlog.title = self.request.get('title')
		backlog.owner = AppUser.get(self.request.get('owner'))
		
		backlog.put()
		
		self.redirect('/')


class HandleItem(webapp.RequestHandler):
	def post(self):
		if self.request.get('id'):
			item = Item.get(self.request.get('id'))
		else:
			item = Item()
		item.title = self.request.get('title')
		item.content = self.request.get('content')
		if self.request.get('backlog_id'):
			item.backlog = Backlog.get(self.request.get('backlog_id'))
		if self.request.get('sprint_id'):
			item.sprint = Sprint.get(self.request.get('sprint_id'))
		if self.request.get('owner'):
			item.owner = AppUser.get(self.request.get('owner'))
		item.estimate = float(self.request.get('estimate'))
		
		item.put()
		
		self.redirect(self.request.get('path'))


class AppUser(db.Model):
	user = db.UserProperty()
	first_name = db.StringProperty()
	last_name = db.StringProperty()
	alert_message = db.StringProperty()


class Project(db.Model):
	title = db.StringProperty()


class Sprint(db.Model):
	title = db.StringProperty()
	project = db.ReferenceProperty(Project)
	start_date = db.DateProperty(auto_now_add=True)
	end_date = db.DateProperty(default=None)


class Backlog(db.Model):
	title = db.StringProperty()
	owner = db.ReferenceProperty(AppUser)


class Item(db.Model):
	title = db.StringProperty()
	content = db.TextProperty(default=None)
	backlog = db.ReferenceProperty(Backlog)
	sprint = db.ReferenceProperty(Sprint)
	project = db.ReferenceProperty(Project)
	owner = db.ReferenceProperty(AppUser)
	estimate = db.FloatProperty(default=0.0)


apps_binding = []

apps_binding.append(('/', MainPage))
apps_binding.append(('/project', ProjectPage))
apps_binding.append(('/project/new', CreateProject))
apps_binding.append(('/sprint/new', CreateSprint))
apps_binding.append(('/backlog', BacklogPage))
apps_binding.append(('/backlog/new', CreateBacklog))
apps_binding.append(('/item/new', HandleItem))
apps_binding.append(('/user', UserPage))
apps_binding.append(('/user/update', UserPage))

application = webapp.WSGIApplication(apps_binding, debug=True)
wsgiref.handlers.CGIHandler().run(application)

