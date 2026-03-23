from knowledge_service import KnowledgeService


def run_pipeline():
    service = KnowledgeService()
    articles = service.refresh_articles()
    print(f"Articles processed successfully: {len(articles)}")


def ask_question():
    service = KnowledgeService()
    question = input("Ask a question: ")
    response = service.ask(question)

    print(response["answer"])
    for index, article in enumerate(response["sources"], start=1):
        print(f"{index}. {article['title']} - {article['link']}")


if __name__ == "__main__":
    run_pipeline()
    ask_question()
