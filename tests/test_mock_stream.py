import time

from app.acquisition.mscl_client import DemoMSCLClient, create_demo_client, SensorInfo


def test_demo_stream_emits_samples():
    stays = [{"stay_id": "T1", "sensor_id": "ACC-01"}]
    client = create_demo_client(stays, default_fs=128, default_acquisition_sec=0.5)
    samples = []

    def callback(sample):
        samples.append(sample)
        client.stop_streaming(sample.sensor_id)

    client.start_streaming("ACC-01", callback)
    time.sleep(0.5)
    assert samples
    sample = samples[0]
    assert sample.acceleration_g.shape[1] == 3
    assert sample.data_format == "acceleration_xyz"


def test_manual_sensor_registration_updates_info():
    client = DemoMSCLClient([])
    client.connect_gateway("demo", 5500)
    info = client.add_manual_sensor(
        sensor_id="ACC-99",
        stay_id="T-Demo",
        sample_rate_hz=128.0,
        axes=["x", "y", "z"],
        data_format="acceleration_x",
        acquisition_duration_sec=2.0,
    )
    assert isinstance(info, SensorInfo)
    assert info.sensor_id == "ACC-99"
    assert info.data_format == "acceleration_x"
    assert info.acquisition_duration_sec == 2.0
