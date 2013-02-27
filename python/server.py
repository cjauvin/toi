import json, re
from pprint import *
from flask import *
from Levenshtein import *
from werkzeug.wsgi import SharedDataMiddleware
import rdflib
from rdflib.graph import Graph
from itertools import *
from nltk.corpus import stopwords
from nltk import SnowballStemmer
from compiler.ast import flatten

# types of query
# --------------
# (1) diabetes            -> Diabetes is a Disease
# (2) diet                -> Diet is a HealthDeterminant
# (3) diet diabetes       -> Diet is a HD which has an effect on Diabetes
# (4) health determinants -> BMI, Diet, etc are HD having effect on Diabetes
#     diabetes
# (5) prevalence          -> PrevalenceIndicator is an Indicator
# (6) diabetes indicators -> DII and DPI are Indicator of Diabetes
# (7) prevalence diabetes -> DiabetesPrevalenceIndicator is an Indicator of Diabetes
# -----------------------------------------------------------------------------------
# (8) prevalence diabetes -> ask for what regions? neighoborhoods, CTs
#     montreal regions
# (9) prevalence diabetes -> DPI for Montreal re
#     montreal 2005

if __name__ == '__main__':

    # http://flask.pocoo.org/snippets/84/
    # To allow using "/vinum_server" prefixed URLs (i.e. WSGIScriptAlias) in the Flask server env
    class CherrokeeFix(object):

        def __init__(self, app, script_name):
            self.app = app
            self.script_name = script_name

        def __call__(self, environ, start_response):
            path = environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '')
            environ['SCRIPT_NAME'] = self.script_name
            environ['PATH_INFO'] = path[len(self.script_name):]
            #assert path[:len(self.script_name)] == self.script_name
            return self.app(environ, start_response)

    # this produces the strange caching bug, i.e. wrong style.css file sent
    # app.wsgi_app = CherrokeeFix(app.wsgi_app, '/vinum_server')
    # app.run(debug=True, port=80, static_files={'/vinum': '/home/christian/vinum/htdocs'})

    app = Flask('PopHR')

    def findTopAncestorConcept(g, what):
        q = """ prefix : <http://www.semanticweb.org/ontologies/2013/1/exmple.owl#>
                prefix owl: <http://www.w3.org/2002/07/owl#>

                select distinct ?lower ?highest
                where { ?highest a owl:Class .
                        ?lower rdfs:subClassOf* ?highest .
                        filter regex(str(?lower), '%s', 'i')
                        ?highest rdfs:subClassOf owl:Thing }
            """ % what
        results = [] # (lev, res)'s
        for r in g.query(q):
            s = [re.match('.*#(.*)', r[i]).group(1) for i in range(2)]
            lev = distance(unicode(what).lower(), s[0].lower())
            results.append((lev, {'lower': s[0], 'highest': s[1]}))
        return sorted(results)[0][1] if results else None


    def findLowHighDiseaseRelationships(g, level, what, disease, relation=None):
        assert level in ['lower', 'higher']
        rel_clause = ''
        if relation:
            rel_clause = "filter regex(str(?relation), '%s', 'i')" % relation
        q = """ prefix : <http://www.semanticweb.org/ontologies/2013/1/exmple.owl#>
                prefix owl: <http://www.w3.org/2002/07/owl#>

                select distinct ?lower ?higher ?relation ?disease
                where { ?lower rdfs:subClassOf+ ?higher .
                        ?higher rdfs:subClassOf owl:Thing .
                        ?lower rdfs:subClassOf ?restriction .
                        ?restriction owl:onProperty ?relation .
                        ?restriction owl:someValuesFrom ?disease .
                        filter regex(str(?%s), '%s', 'i')
                        filter regex(str(?disease), '%s', 'i')
                        %s }
            """ % (level, what, disease, rel_clause)
        #print '\n'.join([l.strip() for l in q.split('\n')])
        results = []
        for r in g.query(q):
            s = [re.match('.*#(.*)', r[i]).group(1) for i in range(4)]
            results.append({'lower': s[0], 'higher': s[3], 'relation': s[1], 'disease': s[2]})
        return results


    def query_offline(query):
        g = Graph()
        g.parse('../PopHR-ToyOnto2.rdf')
        tokens = query.split()
        for p in product(['lower', 'higher'], permutations(tokens, 2)):
            p = flatten(p)
            res = findLowHighDiseaseRelationships(g, p[0], p[1], p[2])
            if res:
                print p
                pprint(res)
                break
        #pprint(findTopAncestorConcept(g, 'diabetes'))


    def concept(s):
        return '<span class="concept">%s</span>' % s


    @app.route('/query', methods=['GET'])
    def query():

        stemmer = SnowballStemmer('english')
        raw_tokens = [w for w in re.split('\W+', request.args['q']) if w.lower() not in set(stopwords.words('english'))]
        tokens = [stemmer.stem(w) for w in raw_tokens]
        token_s2r = dict(zip(tokens, raw_tokens))

        g = Graph()
        g.parse('../PopHR-ToyOnto2.rdf')

        results = []
        matched_tokens = []
        query_type = None

        for n in [3, 2]: # important: begin by most specific query
            if n > len(tokens): continue
            for p in product(['lower', 'higher'], permutations(tokens, n)):
                p = flatten(p)
                p3 = p[3] if n == 3 else None # relation
                results = findLowHighDiseaseRelationships(g, p[0], p[1], p[2], p3)
                if results:
                    query_type = 'disease_relationship'
                    matched_tokens = [token_s2r[w] for w in p[1:]] # first is lower/higher
                    break
            if results: break

        if not results:
            for w in tokens:
                result = findTopAncestorConcept(g, w)
                if result:
                    query_type = 'single_concept'
                    results.append(result)
                    matched_tokens.append(token_s2r[w]) # dont break, there might be another single concepts!

        html_results = []

        if query_type == 'disease_relationship':
            for r in results:
                s = '<p>&gt; %s is a %s in relation %s to %s</p>' % tuple([concept(r[k]) for k in ['lower', 'higher', 'relation', 'disease']])
                html_results.append(s)
        elif query_type == 'single_concept':
             #s = '<p>&gt; %s</p>' % ' and '.join(['%s is a %s' % (concept(r['lower']), concept(r['highest'])) for r in results])
            for r in results:
                s = '<p>&gt; %s is a %s</p>' % tuple([concept(r[k]) for k in ['lower', 'highest']])
                html_results.append(s)
        else:
            html_results.append('<p>&gt; unable to process query</p>')

        html_query = request.args['q']
        for w in matched_tokens:
            html_query = re.sub(w, '<span class="highlighted">%s</span>' % w, html_query)

        return json.dumps({'html_results': html_results, 'html_query': html_query})


    app.wsgi_app = SharedDataMiddleware(CherrokeeFix(app.wsgi_app, '/server'),
                                        {'/': '../htdocs'})
    app.run(debug=True, port=81)

    #query_offline('diabetes prevalence')
