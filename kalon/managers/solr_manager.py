#! /usr/bin/env python3

from flask import current_app
from flask.ext.script import Manager, prompt_bool
from datetime import datetime
from dateutil.parser import parse as dateparse
from functools import partial


def ask_or_abort(fn, yes=False, msg=None):
    if not msg:
        msg = "Are you sure you want to alter {green}{name}{endc}".format(
            green='\033[92m', name=current_app.config['SOLR_URL'], endc='\033[0m')
    if yes or prompt_bool(msg):
        return fn()
    else:
        raise SystemExit('You changed your mind, exiting...')


def solr_manager_factory(solr_collections):
    solr_manager = Manager(usage="Handle Solr operations")

    @solr_manager.option('-y', '--yes', help="Don't ask for confirmation",
                        action='store_true', default=False)
    @solr_manager.option('-s', '--since', default=None,
                         help="Update only element updated since this date")
    def clear(yes, since):
        """Drop the solr database"""
        if since:
            since = dateparse(since)
            q = 'doc_updated_dt:[%sZ TO NOW]' % since.isoformat()
        else:
            q = '*:*'
        ask_or_abort(partial(current_app.solr.delete, q=q), yes=yes)

    @solr_manager.option('-y', '--yes', help="Don't ask for confirmation",
                        action='store_true', default=False)
    @solr_manager.option('-s', '--since', default=None,
                         help="Update only element updated since this date")
    def build(yes, since):
        """Build the solr database"""
        if since:
            since = dateparse(since)
        def _build():
            for col_cls in solr_collections:
                if since:
                    if not hasattr(col_cls, 'doc_updated'):
                        print('%s skipped (no doc_updated field)' % col_cls.__name__)
                        continue
                    objs = col_cls.objects(doc_updated__gte=since)
                else:
                    objs = col_cls.objects()
                print('%s (%s elements)' % (col_cls.__name__, objs.count()),
                      flush=True, end='')
                for i, obj in enumerate(objs):
                    obj.searcher.build_document(obj)
                    if not i % 100:
                        print('.', flush=True, end='')
                print()
        ask_or_abort(_build, yes=yes)

    @solr_manager.option('-y', '--yes', help="Don't ask for confirmation",
                        action='store_true', default=False)
    @solr_manager.option('-s', '--since', default=None,
                         help="Update only element updated since this date")
    def rebuild(yes, since):
        """Rebuild the entire solr index"""
        def _rebuild():
            clear(yes=True, since=since)
            build(yes=True, since=since)
        ask_or_abort(_rebuild, yes=yes)

    return solr_manager
