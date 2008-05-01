#!/usr/bin/env python
#
# Copyright 2008 Todd A. Webb
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""A collaborative Scrum management application built on Google App Engine."""

__author__ = 'Todd Webb'

import os
import cgi
import datetime
import logging

from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext import db
import wsgiref.handlers

# Set to true if we want to have our webapp print stack traces, etc
_DEBUG = True

class BaseRequestHandler(webapp.RequestHandler):
	"""Supplies a common template generation function.

	When you call generate(), we augment the template variables supplied with
	the current user in the 'user' variable and the current webapp request
	in the 'request' variable.

	Adapted from tasks.py by Bret Taylor, Google, Inc. under the same license 
	terms as noted above.
	"""
	def generate(self, template_name, template_values={}):
		values = {
			'request': self.request,
			'user': AppUser.getCurrentUser(),
			'login_url': users.CreateLoginURL(self.request.uri),
			'logout_url': users.CreateLogoutURL('http://' + self.request.host + '/'),
			'debug': self.request.get('deb'),
			'application_name': 'Sprint',
		}
		values.update(template_values)
		directory = os.path.dirname(__file__)
		path = os.path.join(directory, os.path.join('templates', template_name))
		self.response.out.write(template.render(path, values, debug=_DEBUG))


class MainPage(BaseRequestHandler):
	def get(self):
		'''Displays the dashboard page.'''
		# Make sure we have an AppUser session object otherwise send to the user profile to make one
		user = users.get_current_user()
		app_user_query = db.GqlQuery("SELECT * FROM AppUser WHERE user = :1", user)
		app_user = app_user_query.get()
		if not app_user_query.get():
			self.redirect('/user')
		
		# Get all the user's items and the associated sprints and projects. This is sort of inefficient
		# because it gets all projects and sprints then removes the ones that aren't related to user items
		user_projects = [project for project in Project.all().order('title')]
		for project in user_projects:
			sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
			project.sprints = [sprint for sprint in sprint_query]
			for sprint in project.sprints:
				item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND backlog = :2 AND owner = :3 ORDER BY title", sprint, None, app_user)
				sprint.items = [item for item in item_query]
			for sprint in project.sprints[:]:
				if not sprint.items:
					project.sprints.remove(sprint)
		for project in user_projects[:]:
			if not project.sprints:
				user_projects.remove(project)
		
		self.generate('mainpage.html', {
			'user_projects': user_projects,
			'projects': Project.all().order('title'),
			'sprints': Sprint.all().order('title'),
			'backlogs': Backlog.all().order('title'),
			'users': AppUser.all(),
			})


class UserPage(BaseRequestHandler):
	def get(self):
		'''Displays the user profile page.'''
		# Make sure the user has a profile object
		user = AppUser.getCurrentUser()
		if not user:
			user = AppUser()
			user.user = users.GetCurrentUser()
			user.put()
			user.alert_message = "Please update your preferences."
		
		alert = user.alert_message
		user.alert_message = None
		user.put()
		
		self.generate('userpage.html', {
			'alert': alert,
			})


class ProjectPage(BaseRequestHandler):
	'''Displays the project page.'''
	def get(self):
		id = self.request.get('id')
		project = Project.get(id)
		sprint_query = db.GqlQuery("SELECT * FROM Sprint WHERE project = :1 ORDER BY start_date ASC", project)
		project.sprints = [sprint for sprint in sprint_query]
		for sprint in project.sprints:
			item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND backlog = :2 ORDER BY title", sprint, None)
			sprint.items = [item for item in item_query]
			backlog_item_query = db.GqlQuery("SELECT * FROM Item WHERE sprint = :1 AND backlog > :2 ORDER BY backlog, title", sprint, None)
			sprint.backlog_items = [item for item in backlog_item_query]
		
		self.generate('projectpage.html', {
			'project': project, 
			'users': AppUser.all(),
		})


class BacklogPage(BaseRequestHandler):
	'''Displays the backlog page.'''
	def get(self):
		id = self.request.get('id')
		backlog = Backlog.get(id)
		items = db.GqlQuery("SELECT * FROM Item WHERE backlog = :1 ORDER BY title", backlog)

		self.generate('backlogpage.html', {
			'backlog': backlog, 
			'items': items, 
			'users': AppUser.all(),
			'sprints': Sprint.all().order('title'),
		})


class ItemPage(BaseRequestHandler):
	'''Displays the item page.'''
	def get(self):
		id = self.request.get('id')
		item = Item.get(id)
		next = self.request.get('next')

		self.generate('itempage.html', {
			'item': item,
			'next': next,
			'users': AppUser.all(),
		})


class UpdateUserAction(BaseRequestHandler):
	def post(self):
		'''Edits the user profile.'''
		id = self.request.get('id')
		app_user = AppUser.get(id)

		app_user.first_name = self.request.get('first_name')
		app_user.last_name = self.request.get('last_name')
		app_user.alert_message = "You have successfully updated your profile."

		app_user.put()

		self.redirect('/user')


class CreateProjectAction(BaseRequestHandler):
	def post(self):
		project = Project()
		project.title = self.request.get('title')
		
		project.put()
		
		self.redirect('/')


class CreateSprintAction(BaseRequestHandler):
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
		
		self.redirect(self.request.get('next'))


class CreateBacklogAction(BaseRequestHandler):
	def post(self):
		backlog = Backlog()
		backlog.title = self.request.get('title')
		backlog.owner = AppUser.get(self.request.get('owner'))
		
		backlog.put()
		
		self.redirect('/')


class EditItemAction(BaseRequestHandler):
	def post(self):
		item_key = self.request.get('id')
		if item_key:
			item = Item.get(item_key)
		else:
			item = Item(title = " ")
		if self.request.get('title'):
			item.title = self.request.get('title')
		if self.request.get('backlog_id'):
			item.backlog = Backlog.get(self.request.get('backlog_id'))
		if self.request.get('sprint_id'):
			item.sprint = Sprint.get(self.request.get('sprint_id'))
		if self.request.get('owner'):
			if self.request.get('owner') == "none":
				item.owner = None
			else:
				item.owner = AppUser.get(self.request.get('owner'))
		previous_estimate = self.request.get('previous_estimate')
		if self.request.get('estimate'):
			item.estimate = int(self.request.get('estimate'))
			if self.request.get('estimate') == previous_estimate:
				item.last_estimate_date = today()
		
		item.put()
		
		next = self.request.get('next')
		if next:
			self.redirect(self.request.get('next'))
		elif item.backlog:
			backlog_id = str(item.backlog.key())
			self.redirect('/backlog?id=' + backlog_id )
		elif item.sprint:
			project_id = str(item.sprint.project.key())
			self.redirect('/project?id=' + project_id )
		else:
			self.redirect('/')


class AppUser(db.Model):
	user = db.UserProperty()
	first_name = db.StringProperty()
	last_name = db.StringProperty()
	alert_message = db.StringProperty()
	
	@staticmethod
	def getCurrentUser():
		"""docstring for getCurrent"""
		query = AppUser.gql("WHERE user = :1", users.GetCurrentUser())
		return query.get()


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
	title = db.StringProperty(required=True)
	backlog = db.ReferenceProperty(Backlog, default=None)
	sprint = db.ReferenceProperty(Sprint, default=None)
	project = db.ReferenceProperty(Project, default=None)
	owner = db.ReferenceProperty(AppUser, default=None)
	estimate = db.IntegerProperty(default=0)
	last_estimate_date = db.DateProperty(auto_now_add=True)


def main():
	apps_binding = []

	apps_binding.append(('/', MainPage))
	apps_binding.append(('/user', UserPage))
	apps_binding.append(('/project', ProjectPage))
	apps_binding.append(('/backlog', BacklogPage))
	apps_binding.append(('/item', ItemPage))
	apps_binding.append(('/user/update', UpdateUserAction))
	apps_binding.append(('/project/new', CreateProjectAction))
	apps_binding.append(('/sprint/new', CreateSprintAction))
	apps_binding.append(('/backlog/new', CreateBacklogAction))
	apps_binding.append(('/item/new', EditItemAction))
	apps_binding.append(('/item/update', EditItemAction))

	application = webapp.WSGIApplication(apps_binding, debug=_DEBUG)
	wsgiref.handlers.CGIHandler().run(application)


if __name__ == '__main__':
   main()
