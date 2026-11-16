import { useCallback } from "react";
import { ImageCropDialog } from "trm-ui";
import { useI18n } from "../i18n";
import { coverDataUrl, pickCoverImage, setVoiceCover, type VoiceModel } from "../lib/voices";

async function pickImage() {
  const path = await pickCoverImage();
  return path ? coverDataUrl(path) : null;
}

export function CropCoverDialog({ model, onClose, onSaved }: {
  model: VoiceModel;
  onClose: () => void;
  onSaved: (message?: string) => void | Promise<void>;
}) {
  const { t } = useI18n();
  const source = model.cover?.trim();
  const loadInitialImage = useCallback(() => coverDataUrl(source!), [source]);
  return (
    <ImageCropDialog
      name={model.name}
      pickImage={pickImage}
      loadInitialImage={source ? loadInitialImage : undefined}
      onClose={onClose}
      onSave={async (dataUrl) => {
        await setVoiceCover(model.dir, dataUrl);
        await onSaved(t("models.coverSaved"));
      }}
    />
  );
}
