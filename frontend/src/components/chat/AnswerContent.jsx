import ReactMarkdown from 'react-markdown';
import './AnswerContent.css';

export default function AnswerContent({ content = '', streaming = false }) {
  const text = content.replace(/제품\s*선택\s*:\s*[\w:-]+\s*\/?\s*/g, '');
  if (streaming) return <p className="answer-content answer-content--pending">{text}</p>;
  return <div className="answer-content"><ReactMarkdown skipHtml disallowedElements={['img']}
    components={{ a: ({ node, children, ...props }) => <a {...props} target="_blank" rel="noopener noreferrer">{children}</a> }}>
    {text}
  </ReactMarkdown></div>;
}
