#!/usr/bin/env python
# -*- coding:utf-8 -*-
from Cheetah.Template import Template
import jognote

jog = jognote.Jognote('yourid', 'password', '2012/12', '2013/01')
history = jog.export()

template = Template(file='cheetah.template')
template.history = history
print template.respond().encode('utf-8')
