from __future__ import division
import json
import re
import requests
import sys
from nlp_client.wiki_parses import main_page_nps, phrases_for_wiki_field
from id_subject import BinaryField, TermFreqField, preprocess, to_list
from id_subject import build_dict_with_original_values
from id_subject import get_subdomain, guess_from_title_tag

SOLR = 'http://search-s10:8983/solr/xwiki/select'

def identify_subject(wid):
    """For a given wiki ID, return a comma-separated list of top-scoring
    subjects."""
    # Request data from Solr
    params = {'q': 'id:%s' % wid,
              'fl': 'url,hostname_s,domains_txt,top_articles_txt,' +
                    'top_categories_txt',
              'wt': 'json'}

    r = requests.get(SOLR, params=params)
    j = json.loads(r.content)
    response = j['response']['docs'][0]

    # Get lists of NPs or raw data, depending on the field
    hostname = [get_subdomain(url) for url in to_list(response.get('hostname_s'))]
    domains = [get_subdomain(url) for url in to_list(response.get('domains_txt'))]
    sitename = to_list(phrases_for_wiki_field(wid, 'sitename_txt'))
    headline = to_list(phrases_for_wiki_field(wid, 'headline_txt'))
    description = to_list(phrases_for_wiki_field(wid, 'description_txt'))
    top_titles = to_list(response.get('top_articles_txt'))
    top_categories = to_list(response.get('top_categories_txt'))
    title_tag = to_list(guess_from_title_tag(wid))

    fields = [hostname, domains, sitename, headline, description, top_titles,
              top_categories, title_tag]

    # Build dictionary with preprocessed candidate keys and original term values
    candidates = main_page_nps(wid)
    [candidates.extend(field) for field in fields]
    candidates = list(set(candidates))
    candidates = build_dict_with_original_values(candidates)

    # Instantiate BinaryField and TermFreqField objects: avoid rebuilding dicts
    hostname_field = BinaryField(hostname)
    domains_field = TermFreqField(domains)
    sitename_field = BinaryField(sitename)
    headline_field = BinaryField(headline)
    description_field = TermFreqField(description)
    top_titles_field = TermFreqField(top_titles)
    top_categories_field = TermFreqField(top_categories)
    title_tag_field = BinaryField(title_tag)

    def score_candidate(candidate):
        """Return a total score for a candidate across all fields."""
        hostname_score = hostname_field.score(candidate) * 2
        domains_score = domains_field.score(candidate)
        sitename_score = sitename_field.score(candidate)
        headline_score = headline_field.score(candidate)
        description_score = description_field.score(candidate)
        top_titles_score = top_titles_field.score(candidate)
        top_categories_score = top_categories_field.score(candidate)
        title_tag_score = title_tag_field.score(candidate) * 4
        total_score = (hostname_score + domains_score + sitename_score +
                       headline_score + description_score + top_titles_score +
                       top_categories_score + title_tag_score)
        return total_score

    # Combine score of original candidate with scores of individual tokens
    total_scores = {}
    for candidate in candidates:
        total_score = score_candidate(candidate)
        # Add scores of individual tokens, normalized by token count
        if len(candidate) > 1:
            token_score = 0
            for token in list(set(candidate)):
                token_score += score_candidate((token,))
            token_score = token_score / len(candidate)
            total_score += token_score
        total_scores[candidate] = total_score

    # Sort candidates by highest score
    total_scores = sorted([(k, v) for (k, v) in total_scores.items() if 'wiki'
                           not in ''.join(k).lower()], key=lambda x: x[1],
                           reverse=True)

    # DEBUG
    #print response.get('hostname_s')
    #print '\n'.join(['%f\t%s' % (v, k) for (k, v) in total_scores[:5]])

    # Return unstemmed forms of all candidates sharing the top score
    top_score = total_scores[0][1]
    top_terms = []
    for pair in total_scores:
        if pair[1] >= top_score:
            top_terms.append(candidates[pair[0]][0])
        else:
            break

    return '%s,%s,%s' % (wid, response.get('hostname_s'), ','.join(top_terms))

if __name__ == '__main__':
    count = 0
    for line in open('topwams.txt'):
        count += 1
        if count > 100:
            break
        wid = line.strip()
        print identify_subject(wid).encode('utf-8')
