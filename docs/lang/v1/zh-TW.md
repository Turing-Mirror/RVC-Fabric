# RVC-Fabric · zh-TW

| 当前键名 | 原对照表行号 | 应用文本 |
| --- | --- | --- |
| `settings.prewarmTip` | L61 | 程式啟動時自動將目前音色載入至顯示卡，減少開啟即時變聲時的等待時間 |
| `glossary.terms.hubert.detail` | L62 | 用於提取語音中的內容特徵（剝離說話者音色資訊），是所有音色轉換與訓練任務必需的基礎模型。 |
| `glossary.terms.directml.detail` | L63 | Windows 平臺面向 AMD 顯示卡與內建顯示卡的通用硬體加速方案，支援語音轉換推理，暫不支援模型訓練。 |
| `glossary.terms.sr.detail` | L64 | 每秒鐘採集的音訊樣本數。即時變聲時可選擇跟隨音效卡裝置取樣率或音色模型取樣率，通常建議保持預設設定。 |
| `glossary.terms.wasapi.detail` | L65 | Windows 原生音訊通道協定。開啟獨佔模式可進一步降低延遲，但對音效卡硬體相容性要求較高，且啟用期間其他程式將無法同時存取該音訊裝置。 |
| `glossary.terms.block.detail` | L66 | 單次送入模型運算的音訊切片時長。數值越小延遲越低，但硬體運算負載越高，過低時可能導致音訊斷續或失真。 |
| `glossary.terms.crossfade.detail` | L67 | 相鄰音訊切片銜接處的交叉淡化時長，用於消除拼接爆音。數值過小可能產生咔噠聲，過大則會導致聲音模糊。 |
| `glossary.terms.vbcable.detail` | L69 | 一種虛擬音訊線纜驅動：將 RVC Fabric 的變聲輸出路由至虛擬音效卡輸入端，並在通話或直播軟體中將麥克風設為對應的虛擬音效卡輸出端，即可將變聲後的語音傳輸給對方。 |
| `msg.sep.no_request` | L79 | 缺少請求檔案參數 |
| `msg.sep.empty_fields` | L80 | 模型、輸入路徑與輸出路徑均不能為空 |
| `msg.ckpt.info_saved` | L81 | 已儲存模型資訊 |
| `msg.ckpt.extracted` | L82 | 已提取推理模型 |
| `msg.sts.model_is_archive` | L83 | 所選檔案為訓練檢查點（以 G_ 或 D_ 開頭），無法直接用於語音轉換。<br>請先在訓練視窗「進階設定 → 模型提取」裡轉成音色模型，再來轉換。 |
| `msg.train.no_slices` | L84 | 未找到切分後的音訊片段，請檢查資料集中是否包含可讀取的音訊檔案 |
| `msg.train.oom` | L85 | 顯示卡記憶體不足，請調小批次大小（Batch Size）或關閉其他佔用顯示卡記憶體的程式後重試<br>目前批次大小: {batch}<br>{log} |
| `msg.train.resume_f0_partial` | L86 | 偵測到上次音高特徵已提取 {done}/{total}，正在繼續提取剩餘部分… |
| `msg.train.resume_feature_partial` | L87 | 偵測到上次語音特徵已提取 {done}/{total}，正在繼續提取剩餘部分… |
| `s.0f14377cdd` | L96 | 請選擇實體麥克風裝置，請勿選擇虛擬音效卡 |
| `s.1db2e283ac` | L100 | 介面渲染異常：{v0} |
| `s.25865a0d91` | L102 | 正在切換至所選音色… |
| `s.2898cbf891` | L103 | 通常選擇耳機或揚聲器裝置，僅供本機監聽使用 |
| `s.04c4e3b2b3` | L106 | 下載失敗：{e} |
| `s.37f36c5824` | L107 | 已完成效能測試：{a0} |
| `s.1455f353e7` | L114 | 檔案儲存失敗：{e} |
| `s.59f6a509e7` | L115 | 用於調節轉換後的輸出音量增益，平衡最終音量大小 |
| `s.63d89cdb5c` | L118 | 安裝多張 NVIDIA 顯示卡時可在此指定運算裝置；序號順序不代表顯示卡效能高低 |
| `s.703e6f531a` | L121 | 正在校驗並解壓縮大型元件檔案，此階段無法顯示具體百分比，請稍候… |
| `s.7764d6bdd2` | L123 | 背景服務未執行 |
| `s.7dc4ea39fd` | L125 | 訓練處理程序已結束但未傳回結果，請展開底部日誌排查原因 |
| `s.9d7d0dbc49` | L127 | 正在連線：{a0} |
| `s.bc94a9c280` | L131 | 進階選項，通常保持預設即可 |
| `s.c96a64f150` | L134 | 外接音效卡連接說明 |
| `s.f5b3cef9e1` | L136 | 聲音超過此分貝值時觸發動態壓縮；閾值越低，壓縮幅度越大 |
| `s.f7271a7905` | L137 | 語音轉換處理程序已結束，但未產生輸出檔案，請檢視日誌排查 |
| `s.f9e62f8c38` | L138 | 效能測試已結束，但未產生測試報告檔案 |
| `s.ckptModelAHint` | L150 | 主模型（融合時的基準推理模型 A） |
| `s.ckptAlphaHint` | L151 | 模型 A 的權重佔比：1.0 為完全保留 A，0.0 為完全保留 B，0.5 為等比混合 |
| `s.ckptVersionHint` | L152 | 目前標準模型架構均為 v2；僅舊版相容模型需選擇 v1 |
| `s.ckptChangeHint` | L154 | 用於修改推理模型檔案內嵌的說明資訊。請先點擊「檢視」讀取現有資訊後再修改 |
| `s.ckptOnnxOutAuto` | L156 | 留空則預設儲存在原模型同級目錄下（同名 .onnx 檔案） |
| `s.trainSaveWeights` | L157 | 每隔指定儲存週期額外匯出一份可用的推理模型 |
| `s.trainGuideQ6` | L159 | 訓練完成後如何使用？中途關閉程式如何恢復？ |
| `s.dspTipFxTremolo` | L177 | 顫音調變：週期性調節音量包絡，營造復古電台或震顫音效 |
| `s.dspTipFxChorus` | L178 | 合唱效果：疊加多路微移延遲訊號，營造多人齊聲的寬廣聽感 |
| `s.dspTipFxBitcrush` | L179 | 降取樣與位元深度壓縮：降低音訊量化精度，呈現復古像素遊戲的低保真質感 |
| `s.dspTipFxSweep` | L180 | 三角波音高掃頻：使音高在設定的半音區間內週期性往復滑動 |
| `s.dspTipFxPgate` | L181 | 方波音高跳變：使音高在兩個設定檔位之間呈方波階躍切換 |
| `s.dspTipFxRectify` | L182 | 半波整流失真：削去負半週波形，產生類似揚聲器破損的強烈諧波失真 |
| `s.dspTipFxReverse` | L183 | 切片倒放：將即時音訊依短切片逆序回放，產生奇異的倒放語感 |
| `s.dspTipFxRevecho` | L184 | 反向尾音殘響：將近期語音逆序衰減並混入尾音，營造幽邃的殘響氛圍 |
| `s.dspTipPRate` | L185 | 調變或掃頻的變化速率 |
| `s.dspTipPDepth` | L186 | 調變深度的強弱比例 |
| `s.dspTipPVoices` | L187 | 疊加聲部數量（聲部越多合唱感越豐滿） |
| `s.dspTipPTimeMs` | L188 | 回聲延遲時間（毫秒） |
| `s.dspTipPLo` | L190 | 音高掃頻的下限半音值 |
| `s.dspTipPHi` | L190 | 音高掃頻的上限半音值 |
| `s.micTestSilent` | L213 | 未偵測到音訊輸入訊號。請檢查麥克風連接狀態、系統靜音設定，或嘗試切換其他輸入裝置 |
| `s.extraRemoveBusy` | L214 | 該元件正在下載中，請等待下載完成或取消下載後再執行刪除 |
| `s.tearAskBlock` | L218 | 偵測到音訊處理負載過高（可能出現斷續或爆音），是否自動放寬分塊延遲並重新啟動變聲？ |
| `s.faqDownloadSlowH` | L222 | 支援斷點續傳，重試時將從已下載位置繼續。 |
| `s.faqLatencyQ` | L223 | 為什麼說話與聽到變聲之間存在明顯延遲？ |
| `s.chkSnapshotModel` | L225 | 目前所選模型檔案疑似訓練檢查點（以 G_ 或 D_ 開頭），無法直接用於語音轉換<br>{name} |
| `s.errActDownload` | L226 | 前往下載 |
| `s.errActRuntime` | L226 | 配置執行環境 |
| `s.errActExtract` | L226 | 前往模型提取 |
| `s.errActBatch` | L226 | 調整訓練參數 |
| `s.trainSrCost` | L227 | 取樣率越高高頻細節越豐富，但顯示卡記憶體佔用也相應增加；顯示卡記憶體有限時建議選擇較低取樣率。 |
| `s.trainStagesIncomplete` | L229 | 偵測到前置預處理步驟尚未完成。繼續訓練將自動補齊缺失的預處理流程。 |
| `s.cleanupDataset` | L231 | 清理資料集暫存檔案（切分片段與特徵快取） |
| `s.voiceDeleteFailed` | L232 | 刪除失敗。該音色可能正在使用中，請先停止即時變聲或等待轉換任務完成後重試。<br>{e} |
| `s.devAutoNoList` | L234 | 請等待音訊引擎啟動完成後，再執行自動配置 |
| `s.guide.notice.detail` | L237 | 回報問題時，請說明具體的操作步驟、介面提示資訊及異常出現的環節。 |
| `crop.previewBeforeNote` | L241 | 縱向圖片在音色卡片中僅展示中間區域，可透過裁切調整顯示範圍 |
