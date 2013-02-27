import json, re
from pprint import *
from flask import *
from Levenshtein import *
from werkzeug.wsgi import SharedDataMiddleware
import rdflib
from rdflib.graph import Graph
from itertools import permutations
from nltk.corpus import stopwords
from nltk.stem.wordnet import WordNetLemmatizer


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

    # (1, 2, 5)
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


    def findLowHighDiseaseRelationships(g, what, level, disease, relation=None):
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
        for p in permutations(tokens, 2):
            res = findLowHighDiseaseRelationships(g, p[0], 'lower', p[1])
            if res:
                print p
                pprint(res)
                break
        #pprint(findTopAncestorConcept(g, 'diabetes'))


    @app.route('/query', methods=['GET'])
    def query():

        lmtzr = WordNetLemmatizer()
        tokens = re.split('\W+', request.args['q'])
        tokens = [lmtzr.lemmatize(w) for w in tokens if w.lower() not in set(stopwords.words('english'))]

        g = Graph()
        g.parse('../PopHR-ToyOnto2.rdf')

        q1_results = []
        matched = []
        for w in tokens:
            res = findTopAncestorConcept(g, w)
            if res:
                q1_results.append(res)
                matched.append(w)

        html_results = []
        if q1_results:
            q1_results_html = '<p>&gt; %s</p>' % ' and '.join(['<span class="concept">%s</span> is a <span class="concept">%s</span>' % (res['lower'], res['highest']) for res in q1_results])
            html_results.append(q1_results_html)
        else:
            html_results.append('<p>&gt; unable to process query</p>')

        html_query = request.args['q']
        for w in matched:
            html_query = re.sub(w, '<span class="highlighted">%s</span>' % w, html_query)

        return json.dumps({'html_results': html_results, 'html_query': html_query})



    # app.wsgi_app = SharedDataMiddleware(CherrokeeFix(app.wsgi_app, '/server'),
    #                                     {'/': '/home/christian/projects/PopHR-ToyOnto/htdocs'})
    # app.run(debug=True, port=81)

    query_offline('diabetes prevalence')
