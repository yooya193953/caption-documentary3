                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-zinc-700 mb-2">参照記事</label>
                <textarea
                  value={formData.reference_links}
                  onChange={(e) => setFormData({ ...formData, reference_links: e.target.value })}
                  className="w-full px-4 py-3 border border-zinc-300 rounded-lg font-medium focus:outline-none focus:ring-2 focus:ring-primary font-mono text-sm"
                  placeholder="記事の最後に表示される参照リンク（マークダウン対応）&#10;例:&#10;- [記事タイトル](https://example.com)&#10;- [別の記事](https://example.com/article)"
                  rows={6}
                />
              </div>
            </div>
          </div>

          {isEdit && (
            <div className="bg-white rounded-xl border border-zinc-200 p-6">
              <div className="flex items-center gap-3 mb-4">
                <Share2 className="w-6 h-6 text-zinc-900" />
                <h2 className="text-2xl font-black text-zinc-900">ドラフト共有リンク</h2>
              </div>
              <p className="text-sm text-zinc-600 mb-6">
                認証なしでドラフトをプレビューできる共有リンクを生成します
              </p>

              {shareToken ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 p-4 bg-green-50 border border-green-200 rounded-lg">
                    <input
                      type="text"
                      value={`${window.location.origin}/preview/${shareToken}`}
                      readOnly
                      className="flex-1 px-4 py-2 bg-white border border-green-300 rounded-lg font-mono text-sm focus:outline-none"
                    />
                    <button
                      onClick={copyShareLink}
                      className="px-4 py-2 bg-green-600 text-white font-bold rounded-lg hover:bg-green-700 transition-colors flex items-center gap-2"
                    >
                      {copied ? (
                        <>
                          <Check className="w-5 h-5" />
                          コピー済み
                        </>
                      ) : (
                        <>
                          <Copy className="w-5 h-5" />
                          コピー
                        </>
                      )}