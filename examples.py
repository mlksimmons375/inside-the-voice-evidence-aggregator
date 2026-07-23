#!/usr/bin/env python3
"""
Quick Examples - Evidence Aggregator

Copy-paste examples for common tasks
"""

from evidence_aggregator import EvidenceAggregator
import os

# Example 1: Complete evidence gathering for Episode 1
def example_full_episode():
    """Run all searches for one episode"""
    
    agg = EvidenceAggregator(episode_num=1, topic="breath control")
    
    # Reddit posts
    agg.search_reddit(subreddit="singing", limit=10)
    
    # YouTube comments
    agg.search_youtube_comments()
    
    # Research papers
    agg.search_google_scholar()
    
    # Video clips
    agg.search_video_clips()
    
    # Generate report
    agg.generate_evidence_stack_report()
    
    print(f"\n✅ Complete! Check: {agg.output_dir}")


# Example 2: Add clips manually (Tier 1: Passive Collection)
def example_bookmark_clips():
    """While browsing, save clips for later"""
    
    agg = EvidenceAggregator(episode_num=1, topic="breath")
    
    # Bookmark a YouTube clip
    agg.add_clip_bookmark(
        url="https://youtube.com/watch?v=example123",
        timestamp="2:35-2:48",
        description="Singer runs out of breath on high note, visible strain",
        source_type="youtube"
    )
    
    # Bookmark a TikTok
    agg.add_clip_bookmark(
        url="https://tiktok.com/@user/video/123",
        timestamp="0:15",
        description="Viral singing fail - breath control breakdown",
        source_type="tiktok"
    )
    
    # Bookmark an award show moment
    agg.add_clip_bookmark(
        url="https://youtube.com/watch?v=grammys2024",
        timestamp="1:23:45",
        description="Grammy performance - artist struggles with breath on final note",
        source_type="tv_performance"
    )
    
    print("✅ Clips saved to database")


# Example 3: Scrape specific articles
def example_articles():
    """Scrape vocal pedagogy articles"""
    
    agg = EvidenceAggregator(episode_num=1, topic="resonance")
    
    article_urls = [
        "https://example.com/vocal-pedagogy/resonance-basics",
        "https://example.com/singing-tips/breath-support"
    ]
    
    agg.search_articles(urls=article_urls)
    agg.generate_evidence_stack_report()


# Example 4: Just Reddit and YouTube (common combo)
def example_social_media_only():
    """Quick evidence from social media"""
    
    agg = EvidenceAggregator(episode_num=2, topic="high notes")
    
    # Reddit
    agg.search_reddit(subreddit="singing", limit=15)
    
    # YouTube
    agg.search_youtube_comments(query="high notes singing tutorial")
    
    # Report
    agg.generate_evidence_stack_report()


# Example 5: Targeted clip search (Tier 2)
def example_targeted_clips():
    """Search for specific types of clips after choosing topic"""
    
    agg = EvidenceAggregator(episode_num=3, topic="vocal tension")
    
    # Custom search terms
    keywords = [
        "singer struggles high notes live",
        "vocal tension performance fail",
        "tight throat singing problem"
    ]
    
    agg.search_video_clips(keywords=keywords, clip_type="performance_stress")
    
    print("✅ Found performance stress clips")


# Example 6: Research papers only
def example_papers_only():
    """Just gather academic sources"""
    
    agg = EvidenceAggregator(episode_num=4, topic="vocal fold coordination")
    
    # Scholar search
    agg.search_google_scholar(query="vocal fold coordination phonation", limit=5)
    
    # Generate report
    agg.generate_evidence_stack_report()


# Example 7: Build clip database over time
def example_build_clip_library():
    """Passive collection - run this whenever you find a good clip"""
    
    # Episode doesn't matter - this builds your overall library
    agg = EvidenceAggregator(episode_num=0, topic="clip_library")
    
    # Add clips as you find them
    clips = [
        {
            "url": "https://youtube.com/watch?v=abc",
            "timestamp": "3:15",
            "description": "Artist cracks on high note - studio vs live comparison",
            "source_type": "youtube"
        },
        {
            "url": "https://youtube.com/watch?v=def",
            "timestamp": "1:45",
            "description": "Voice coach explaining breath support mechanism",
            "source_type": "youtube"
        },
        {
            "url": "https://tiktok.com/@singer/video/xyz",
            "timestamp": "0:08",
            "description": "Viral singing fail - breath runs out mid-phrase",
            "source_type": "tiktok"
        }
    ]
    
    for clip in clips:
        agg.add_clip_bookmark(**clip)
    
    print(f"✅ Added {len(clips)} clips to library")


# Example 8: Pre-production workflow
def example_episode_workflow():
    """Complete pre-production for one episode"""
    
    print("📋 EPISODE PRE-PRODUCTION WORKFLOW\n")
    
    # Step 1: Choose topic
    episode_num = 1
    topic = "breath control"
    
    print(f"Episode {episode_num}: {topic}")
    print("-" * 50)
    
    # Step 2: Gather all evidence
    print("\n🔍 Step 1: Gathering evidence...")
    agg = EvidenceAggregator(episode_num, topic)
    
    agg.search_reddit(limit=10)
    agg.search_youtube_comments()
    agg.search_google_scholar(limit=5)
    agg.search_video_clips()
    
    # Step 3: Generate report
    print("\n📊 Step 2: Generating report...")
    agg.generate_evidence_stack_report()
    
    # Step 4: Review
    print("\n✅ Step 3: Review your evidence:")
    print(f"   - Report: {agg.output_dir}/evidence_report.md")
    print(f"   - Reddit: {agg.evidence_dir}/reddit/")
    print(f"   - YouTube: {agg.evidence_dir}/youtube_comments.txt")
    print(f"   - Papers: {agg.research_dir}/research_papers.txt")
    print(f"   - Clips: {agg.clips_dir}/found_clips.txt")
    
    print("\n📝 Next: Review evidence → Create flashcards → Outline episode")


if __name__ == "__main__":
    import sys
    
    examples = {
        "1": ("Full episode gathering", example_full_episode),
        "2": ("Bookmark clips", example_bookmark_clips),
        "3": ("Scrape articles", example_articles),
        "4": ("Social media only", example_social_media_only),
        "5": ("Targeted clips", example_targeted_clips),
        "6": ("Research papers", example_papers_only),
        "7": ("Build clip library", example_build_clip_library),
        "8": ("Complete workflow", example_episode_workflow)
    }
    
    print("="*60)
    print("📚 EVIDENCE AGGREGATOR - EXAMPLES")
    print("="*60)
    print("\nAvailable examples:")
    for num, (name, _) in examples.items():
        print(f"  {num}. {name}")
    
    print("\nUsage: python examples.py [number]")
    print("Example: python examples.py 1\n")
    
    if len(sys.argv) > 1:
        choice = sys.argv[1]
        if choice in examples:
            name, func = examples[choice]
            print(f"\nRunning example: {name}")
            print("="*60 + "\n")
            func()
        else:
            print(f"❌ Invalid choice: {choice}")
    else:
        print("💡 Tip: Run 'python examples.py 8' for the complete workflow")
