import requests
from bs4 import BeautifulSoup
import json
import csv
import os
from datetime import datetime
from flask import Flask, request, render_template_string, send_from_directory, jsonify

app = Flask(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1"
}

HTML_FORM = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <title>WordPress Scraper</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 800px; margin: 40px auto; padding: 20px; background: #f9f9f9; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
    h1 { color: #333; }
    label { display: block; margin-top: 10px; }
    input[type=text], input[type=number] { width: 100%; padding: 8px; margin-top: 5px; }
    button { margin-top: 20px; padding: 10px 15px; background-color: #4CAF50; color: white; border: none; border-radius: 5px; cursor: pointer; }
    button:hover { background-color: #45a049; }
    #loading { display: none; margin-top: 20px; color: #444; font-style: italic; }
    .post { border-bottom: 1px solid #ccc; padding: 10px 0; }
    .post img { max-width: 100px; display: block; margin-bottom: 5px; }
    .download-links { margin-top: 20px; }
    .download-links a { display: inline-block; margin-right: 15px; }
    .error { color: red; margin-top: 20px; font-weight: bold; }
  </style>
</head>
<body>
  <h1>WordPress Scraper</h1>
  <form id=\"scrape-form\" action=\"/scrape\" method=\"post\">
    <label>Base URL:
      <input name=\"url\" required value=\"https://techpoint.africa/subject/startups/\">
    </label>
    <label>Filename:
      <input name=\"filename\" value=\"\">
    </label>
    <label>Max Pages (0 = all):
      <input name=\"max_pages\" type=\"number\" min=\"0\" value=\"5\">
    </label>
    <label><input name=\"include_content\" type=\"checkbox\" checked> Include Full Content?</label>
    <label><input name=\"save_csv\" type=\"checkbox\" checked> Save as CSV?</label>
    <button type=\"submit\">Start Scraping</button>
  </form>
  <div id=\"loading\">⏳ Scraping in progress... please wait.</div>
  <div class=\"error\" id=\"error\"></div>
  <div class=\"download-links\" id=\"downloads\"></div>
  <div id=\"results\"></div>
  <script>
    const form = document.getElementById('scrape-form');
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const downloads = document.getElementById('downloads');
    const error = document.getElementById('error');
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      loading.style.display = 'block';
      results.innerHTML = '';
      downloads.innerHTML = '';
      error.textContent = '';
      const formData = new FormData(form);
      try {
        const response = await fetch('/scrape', {
          method: 'POST',
          body: formData
        });
        const data = await response.json();
        loading.style.display = 'none';
        if (data.error) {
          error.textContent = data.error;
        } else if (data.posts) {
          data.posts.forEach(post => {
            const div = document.createElement('div');
            div.className = 'post';
            div.innerHTML = `<h3><a href="${post.url}" target="_blank">${post.title}</a></h3>` +
                            (post.featured_image ? `<img src="${post.featured_image}" alt="Image">` : '') +
                            `<p>${post.summary || ''}</p>`;
            results.appendChild(div);
          });
          downloads.innerHTML = `
            <strong>Download:</strong>
            <a href="/download/${data.file}" download>JSON File</a>
            ${data.csv_file ? `<a href="/download/${data.csv_file}" download>CSV File</a>` : ''}
          `;
        }
      } catch (err) {
        loading.style.display = 'none';
        error.textContent = 'An unexpected error occurred.';
      }
    });
  </script>
</body>
</html>
"""  # Keep the form unchanged

@app.route("/", methods=["GET"])
def form():
    return render_template_string(HTML_FORM)

@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        BASE_URL = request.form['url'].strip()
        filename_input = request.form['filename'].strip()
        max_pages = int(request.form.get('max_pages', 0))
        include_content = 'include_content' in request.form
        save_csv = 'save_csv' in request.form

        timestamp = datetime.now().strftime("%d%m%y%H%M%S")
        filename = filename_input if filename_input else f"scrape_{timestamp}.json"

        all_posts = []
        page = 1

        while True:
            url = f"{BASE_URL}page/{page}/" if page > 1 else BASE_URL
            print(f"Fetching: {url}")
            res = requests.get(url, headers=HEADERS)
            if res.status_code != 200:
                return jsonify({"error": f"Failed to fetch page {page}. Status code: {res.status_code}"})

            soup = BeautifulSoup(res.text, 'html.parser')
            articles = soup.select('article')
            if not articles:
                articles = soup.select(".td_module_10, .td_module_11, .td_module_1")
            if not articles:
                return jsonify({"error": f"No articles found on page {page}. The site structure may have changed."})

            for article in articles:
                title_tag = article.find('h3') or article.find('h2')
                link = title_tag.find('a')['href'] if title_tag and title_tag.find('a') else None
                title = title_tag.get_text(strip=True) if title_tag else None
                summary_tag = article.find('p') or article.find('div', class_='td-excerpt')
                summary = summary_tag.get_text(strip=True) if summary_tag else None

                content = None
                featured_image = None

                if link and include_content:
                    try:
                        detail_res = requests.get(link, headers=HEADERS)
                        if detail_res.status_code == 200:
                            detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
                            content_div = detail_soup.select_one('div.entry-content, div.td-post-content')
                            content = content_div.get_text(strip=True) if content_div else None
                            img_tag = detail_soup.select_one('figure img, img.wp-post-image, .td-post-featured-image img')
                            featured_image = img_tag['src'] if img_tag and img_tag.has_attr('src') else None
                    except Exception as ex:
                        print(f"Failed to fetch detail page: {link} | Error: {ex}")

                if title and link:
                    all_posts.append({
                        "title": title,
                        "url": link,
                        "summary": summary,
                        "content": content,
                        "featured_image": featured_image
                    })

            page += 1
            if max_pages and page > max_pages:
                break

        if not all_posts:
            return jsonify({"error": "Scraping completed but no posts were found. Check the URL and site structure."})

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(all_posts, f, ensure_ascii=False, indent=2)

        csv_file = None
        if save_csv:
            csv_file = os.path.splitext(filename)[0] + ".csv"
            with open(csv_file, "w", encoding="utf-8", newline="") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=["title", "url", "summary", "content", "featured_image"])
                writer.writeheader()
                for post in all_posts:
                    writer.writerow(post)

        return jsonify({"message": f"✅ Scraped {len(all_posts)} posts.", "file": filename, "csv_file": csv_file, "posts": all_posts[:20]})
    except Exception as e:
        return jsonify({"error": f"Error: {str(e)}"})

@app.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory('.', filename, as_attachment=True)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
