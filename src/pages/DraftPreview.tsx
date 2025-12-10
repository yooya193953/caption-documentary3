import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { supabase } from '../lib/supabase';
import MarkdownRenderer from '../components/MarkdownRenderer';
import { Calendar, User, Tag, AlertCircle } from 'lucide-react';
import { format } from 'date-fns';

interface Article {
  id: string;
  title: string;
  lead_text: string | null;
  content: string;
  featured_image: string | null;
  created_at: string;
  updated_at: string;
  authors: {
    name: string;
    bio: string | null;
  };
  categories: {
    name: string;
    slug: string;
  } | null;
  tags: string[];
}

export default function DraftPreview() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDraft() {
      if (!token) {
        setError('共有トークンが見つかりません');
        setLoading(false);
        return;
      }

      try {
        const { data: shareToken, error: tokenError } = await supabase
          .from('share_tokens')
          .select('article_id, is_active, expires_at')
          .eq('token', token)
          .maybeSingle();

        if (tokenError) throw tokenError;

        if (!shareToken) {
          setError('無効な共有リンクです');
          setLoading(false);
          return;
        }

        if (!shareToken.is_active) {
          setError('この共有リンクは無効化されています');
          setLoading(false);
          return;
        }

        if (shareToken.expires_at && new Date(shareToken.expires_at) < new Date()) {
          setError('この共有リンクは期限切れです');
          setLoading(false);
          return;
        }

        const { data: articleData, error: articleError } = await supabase
          .from('articles')
          .select(`
            id,
            title,
            lead_text,
            markdown_content,
            featured_image_url,
            created_at,
            updated_at,
            tags,
            authors (
              name,
              bio
            ),
            categories (
              name,
              slug
            )
          `)
          .eq('id', shareToken.article_id)
          .single();

        if (articleError) throw articleError;

        setArticle({
          ...articleData,
          content: articleData.markdown_content,
          featured_image: articleData.featured_image_url,
        });
      } catch (err) {
        console.error('Error loading draft:', err);
        setError('記事の読み込みに失敗しました');
      } finally {
        setLoading(false);
      }
    }

    loadDraft();
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">読み込み中...</p>
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full text-center">
          <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-gray-900 mb-2">アクセスエラー</h2>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => navigate('/')}
            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors"
          >
            ホームへ戻る
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-yellow-500 text-white py-3 px-4 text-center font-medium">
        <span className="inline-flex items-center gap-2">
          <AlertCircle className="w-5 h-5" />
          これはプレビューです - 公開されていません
        </span>
      </div>

      <article className="max-w-4xl mx-auto px-4 py-12">
        {article.featured_image && (
          <div className="mb-8 rounded-xl overflow-hidden shadow-lg">
            <img
              src={article.featured_image}
              alt={article.title}
              className="w-full h-auto object-cover"
            />
          </div>
        )}

        {article.categories && (
          <div className="mb-4">
            <span className="inline-block bg-blue-100 text-blue-800 text-sm font-medium px-3 py-1 rounded-full">
              {article.categories.name}
            </span>
          </div>
        )}

        <h1 className="text-4xl md:text-5xl font-bold text-gray-900 mb-6 leading-tight">
          {article.title}
        </h1>

        {article.lead_text && (
          <p className="text-xl text-gray-600 mb-8 leading-relaxed">
            {article.lead_text}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-6 mb-8 pb-8 border-b border-gray-200">
          <div className="flex items-center gap-2 text-gray-600">
            <User className="w-5 h-5" />
            <span className="font-medium">{article.authors.name}</span>
          </div>
          <div className="flex items-center gap-2 text-gray-600">
            <Calendar className="w-5 h-5" />
            <span>{format(new Date(article.updated_at), 'yyyy年MM月dd日')}</span>
          </div>
        </div>

        <div className="prose prose-lg max-w-none mb-8">
          <MarkdownRenderer content={article.content} />
        </div>

        {article.tags && article.tags.length > 0 && (
          <div className="mt-12 pt-8 border-t border-gray-200">
            <div className="flex items-center gap-2 flex-wrap">
              <Tag className="w-5 h-5 text-gray-500" />
              {article.tags.map((tag) => (
                <span
                  key={tag}
                  className="bg-gray-100 text-gray-700 px-3 py-1 rounded-full text-sm"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </article>
    </div>
  );
}
