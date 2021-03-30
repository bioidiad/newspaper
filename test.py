from newspaper import Article
import requests as req

def get_article(html):
    article = Article(html)
    article.parse()
    print(article.text)


if __name__ == '__main__':
    url = 'https://betterprogramming.pub/a-visual-guide-to-set-comparisons-in-python-6ab7edb9ec41'
    resp = req.get(url)

    if resp.status_code == 200:
        html = resp.text
        get_article(html)

    # article.download()
