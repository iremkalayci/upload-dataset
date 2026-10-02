
from sdks.novavision.src.helper.package import PackageHelper

from components.UploadDataset.src.models.PackageModel import (
    PackageConfigs,
    ConfigExecutor,
    PackageModel,
    OutputImage,
    UploadDatasetOutputs,
    UploadDatasetResponse,
    UploadDatasetExecutor,
)


def build_response(context):
    output_image = OutputImage(value=context.result)

    upload_dataset_outputs = UploadDatasetOutputs(
        outputImage=output_image
    )

    upload_dataset_response = UploadDatasetResponse(
        outputs=upload_dataset_outputs
    )

    upload_dataset_executor = UploadDatasetExecutor(
        value=upload_dataset_response
    )

    executor = ConfigExecutor(
        value=upload_dataset_executor
    )

    package_configs = PackageConfigs(executor=executor)

    package = PackageHelper(
        packageModel=PackageModel,
        packageConfigs=package_configs
    )

    package_model = package.build_model(context)

    return package_model
