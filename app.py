import uuid
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from signals import classify_with_llm, compute_stylometric_score, compute_confidence
from database import init_db, log_submission, get_log

load_dotenv()

app = Flask(__name__)
init_db()



def generate_label(score: float, attribution: str) -> str:
    pct = round(score * 100)
    if attribution == "likely_ai":
        return (
            f"This content shows strong indicators of AI generation (confidence: {pct}%). "
            "Our analysis detected consistent sentence structure and limited stylistic variation "
            "typical of AI-generated writing. If this is your original work, you have the right "
            "to appeal this classification below."
        )
    if attribution == "uncertain":
        return (
            f"We could not confidently determine the origin of this content (confidence: {pct}%). "
            "The writing shows mixed signals — some characteristics associated with AI generation, "
            "some consistent with human authorship. No action has been taken. This label is shown "
            "for transparency only."
        )
    return (
        f"This content appears to be human-written (confidence: {pct}%). "
        "Our analysis found natural variation in style and structure consistent with human authorship."
    )


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()

    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({"error": "Request must include 'text' and 'creator_id'"}), 400

    text = data["text"]
    creator_id = data["creator_id"]
    content_id = str(uuid.uuid4())

    llm_result = classify_with_llm(text)
    llm_score = llm_result["ai_probability"]
    style_score = compute_stylometric_score(text)
    confidence_result = compute_confidence(llm_score, style_score)

    confidence = confidence_result["score"]
    attribution = confidence_result["attribution"]
    label = generate_label(confidence, attribution)

    log_submission(content_id, creator_id, attribution, confidence, llm_score, style_score)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "style_score": style_score,
        "label": label
    })


@app.route("/log", methods=["GET"])
def log():
    return jsonify({"entries": get_log()})


if __name__ == "__main__":
    app.run(debug=True, port=5001)
