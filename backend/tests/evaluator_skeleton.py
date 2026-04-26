import json
import time

def generate_outline_stub(topic, depth):

    time.sleep(1) # 模拟处理耗时
    return {
        "title": f"关于 {topic} 的报告",
        "meta": {"retrieval_depth": depth, "generated_at": "2026-04-26T20:00:00Z"}
    }

def run_evaluation(dataset_path):
    with open(dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    results = []
    for item in dataset:
        start_time = time.time()
        output = generate_outline_stub(item['topic'], item['expected_depth'])
        latency = time.time() - start_time
        
        # 评分逻辑（目前为基础检查）
        score = 1.0 if "title" in output else 0.0
        results.append({
            "task_id": item['task_id'],
            "latency": latency,
            "score": score
        })
    
    with open('docs/evaluation/report_v0.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("评测完成，报告已生成至 docs/evaluation/report_v0.json")

if __name__ == "__main__":
    run_evaluation('docs/evaluation/dataset_v0.json')