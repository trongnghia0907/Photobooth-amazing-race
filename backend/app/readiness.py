"""Private operator diagnostics; no hardware commands or external probes."""
import platform
import shutil


def report(repo, printing, camera):
    settings=repo.settings
    free=shutil.disk_usage(settings.storage_root).free
    cap=camera.adapter.get_capabilities()
    printer=printing.config()
    blockers=[]
    if free < settings.min_free_space_mb*1024*1024:blockers.append('Storage is below the configured free-space reserve.')
    sharing=repo.sharing.configuration()
    if not sharing['configured']:blockers.append('PUBLIC_BASE_URL is missing or invalid; final QR cannot be created.')
    if settings.operation_mode=='event':
        if cap.demo or not (cap.capture and cap.physical_shutter and cap.original_file and cap.hardware_verified):
            blockers.append('Physical camera/SDK and original JPG transfer have not been verified on this host.')
        if settings.printer_mode=='mock' or not printer['available']:blockers.append('An explicitly configured physical printer is not ready.')
    return {'operation_mode':settings.operation_mode,'os':platform.system(),'os_version':platform.release(),
            'architecture':platform.machine(),'free_space_mb':free//(1024*1024),'reserve_mb':settings.min_free_space_mb,
            'camera_model':settings.camera_model or 'NOT CONFIGURED','printer_mode':settings.printer_mode,
            'blockers':blockers,'hardware_acceptance':'NOT TESTED by software diagnostics',
            'network_acceptance':'Operator must scan QR over the intended Wi-Fi/4G/5G; configuration is not a connectivity test.'}
