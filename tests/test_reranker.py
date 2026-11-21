"""Le reranker tourne sans sentence_transformers (contrainte Railway)."""
import reranker


def test_lexical_engine_is_active_without_heavy_deps():
    assert reranker.engine() in {"lexical", "cross"}
    assert reranker.threshold() > 0


def test_typos_and_sms_are_understood():
    assert reranker.is_relevant(reranker.lexical_score("kel est le prix dun logo", "prix logo"))
    assert reranker.is_relevant(reranker.lexical_score("comb1 pour un site", "c'est combien un site"))
    assert reranker.is_relevant(reranker.lexical_score("slt cv", "bonjour"))


def test_nonsense_and_offtopic_are_rejected():
    assert not reranker.is_relevant(reranker.lexical_score("blablabla xyz qsdf", "prix logo"))
    assert not reranker.is_relevant(
        reranker.lexical_score("quelle est la capitale du japon", "prix logo")
    )


def test_synonyms_are_matched():
    # « robot » et « chatbot » sont le même métier
    assert reranker.lexical_score("je veux un robot", "c'est quoi un chatbot") > 0.3


def test_rerank_orders_candidates():
    candidates = [
        (0.9, "réponse hors sujet", "quelle est la capitale du japon"),
        (0.5, "bonne réponse", "kel est le prix dun logo"),
    ]
    ranked = reranker.rerank("kel est le prix dun logo", candidates)
    assert ranked and ranked[0][0] == "bonne réponse"
