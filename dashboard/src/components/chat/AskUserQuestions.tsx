type Props = {
  questions: string[];
  onSelect: (question: string) => void;
  disabled?: boolean;
};

export default function AskUserQuestions({ questions, onSelect, disabled = false }: Props) {
  if (questions.length === 0) return null;

  return (
    <div className="ask-user-questions">
      {questions.map((question) => (
        <button
          key={question}
          type="button"
          className="ask-user-question-btn"
          disabled={disabled}
          onClick={() => onSelect(question)}
        >
          <span className="ask-user-question-text">{question}</span>
          <span className="material-icons-round ask-user-question-arrow">arrow_forward</span>
        </button>
      ))}
    </div>
  );
}
