#!/bin/bash

cd /opt/claude/projects/printops-website
git add .
git commit -m "Updated website"
git push

cd /opt/claude/projects/printops-wiki
git add .
git commit -m "Updated Wiki"
git push

cd /opt/claude/projects/printops-sponsors-portal
git add .
git commit -m "Updated portal"
git push
