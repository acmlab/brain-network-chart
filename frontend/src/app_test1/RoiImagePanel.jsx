import { useEffect, useState } from 'react';

export const RoiImagePanel = ({ roiName }) => {
  const [roiId, setRoiId] = useState(null);

  useEffect(() => {
    if (!roiName) return;
    const cleanName = roiName.replace(/^Hub:\s*/, '');
    fetch(`/api/roi-id?name=${encodeURIComponent(cleanName)}`)
      .then(res => res.json())
      .then(data => setRoiId(data.roi_id))
      .catch(() => setRoiId(null));
  }, [roiName]);

  if (!roiName) {
    return (
      <div className="h-full flex flex-col items-center justify-center border border-dashed border-slate-300 rounded-xl bg-slate-50">
        <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center mb-2">
          <svg className="w-5 h-5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        </div>
        <p className="text-xs text-slate-500">Click a node to view ROI</p>
      </div>
    );
  }

  if (!roiId) {
    return (
      <div className="h-full flex items-center justify-center border border-red-200 rounded-xl bg-red-50">
        <p className="text-xs text-red-500">ROI image not found</p>
      </div>
    );
  }

  return (
    <div className="h-full border border-slate-200 rounded-xl overflow-hidden bg-white">
      <div className="px-3 py-2 border-b border-slate-100 bg-slate-50 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-indigo-400" />
        <span className="text-xs font-semibold text-slate-600 truncate">{roiName}</span>
      </div>
      <div className="p-2">
        <img src={`/api/roi_figs/mask${roiId}_roi.png`} alt={roiName} className="w-full h-auto object-contain" />
      </div>
    </div>
  );
};
